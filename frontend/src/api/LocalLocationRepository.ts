import { detailEnvelopeSchema, envelopeSchema, type WireLocation } from './wireSchema';
import type { ApiError } from './errors';
import type { Location } from '../domain/location';
import { isTaxonomyPrimaryKey, TAXONOMY_PRIMARY_KEYS, TAXONOMY_VERSION, type TaxonomyAssignment, type TaxonomyPrimaryKey } from '../domain/taxonomy';

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export type LocalProfile = 'official' | 'secondary' | 'community';
export type LocationFilters = Readonly<{ q?: string | undefined; country_code?: string | undefined; region?: string | undefined; category?: string | undefined; category_keys?: readonly TaxonomyPrimaryKey[] | undefined; source_type?: string | undefined; display_precision?: string | undefined; lifecycle_status?: string | undefined; min_lon?: number | undefined; min_lat?: number | undefined; max_lon?: number | undefined; max_lat?: number | undefined; latitude?: number | undefined; longitude?: number | undefined; radius_km?: number | undefined; cursor?: string | undefined; offset?: number | undefined; limit?: number | undefined }>;
export type LocalListResult = Readonly<{ locations: readonly Location[]; releaseId: string; profile: LocalProfile; coverageNote: string; coverageScope?: string; countSemantics?: string; nextCursor: string | null; ruleset?: string }>;
export const localOrigin = (value: string | undefined): string | undefined => { if (!value) return undefined; const url = new URL(value); if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '::1'].includes(url.hostname)) throw new Error('Local API origin must be loopback HTTP.'); return url.origin; };
const fail = (kind: ApiError['kind'], message: string, status?: number, code?: string): ApiError => Object.assign(new Error(message), { kind, ...(status === undefined ? {} : { status }), ...(code ? { code } : {}) });
export const mapWireLocation = (r: WireLocation): Location => {
  const rawCategories = r.taxonomy_primary_categories ?? (r.taxonomy_display_category ? [r.taxonomy_display_category] : []);
  const primaryCategories = [...new Set((rawCategories.length ? rawCategories : ['unclassified']).map(key => isTaxonomyPrimaryKey(key) ? key : 'unclassified' as const))]
    .sort((a, b) => TAXONOMY_PRIMARY_KEYS.indexOf(a) - TAXONOMY_PRIMARY_KEYS.indexOf(b));
  const assignments: readonly TaxonomyAssignment[] = (r.taxonomy_assignments ?? []).map(item => ({
    primaryKey: isTaxonomyPrimaryKey(item.primary_key) ? item.primary_key : 'unclassified', leafKey: item.leaf_key ?? null, leafLabel: item.leaf_label ?? null,
    sourceCodeReference: item.source_code_reference ?? null, sourceLabelReference: item.source_label_reference ?? null,
    sourceCode: item.source_code ?? null, sourceLabel: item.source_label ?? null,
    method: item.method, status: item.status, taxonomyVersion: item.taxonomy_version,
    crosswalkVersion: item.crosswalk_version ?? null, rulesetVersion: item.ruleset_version ?? null,
    observationId: item.observation_id ?? null, sourceRecordId: item.source_record_id ?? null, artifactId: item.artifact_id ?? null,
  }));
  const category = r.taxonomy_display_category && isTaxonomyPrimaryKey(r.taxonomy_display_category)
    ? r.taxonomy_display_category
    : r.taxonomy_display_category !== undefined ? 'unclassified'
      : primaryCategories.length === 1 ? primaryCategories[0]! : 'unclassified';
  return {
  id: r.facility_id, name: r.canonical_name ?? 'Unnamed candidate record', region: r.city ?? r.country_code, category: r.category,
  sourceId: r.provenance_source_id,
  taxonomy: {
    displayCategory: category as TaxonomyPrimaryKey,
    primaryCategories,
    leafActivities: [...new Map((r.taxonomy_leaf_activities ?? []).map(item => [item.key, item])).values()].sort((a, b) => a.key.localeCompare(b.key)),
    assignments,
    taxonomyVersion: assignments[0]?.taxonomyVersion ?? TAXONOMY_VERSION,
  },
  lat: r.latitude, lon: r.longitude, observed: r.last_observed_at ?? r.first_observed_at ?? 'unknown', source: r.provenance_source_name,
  evidence: {
    sourceType: r.source_type, factualReviewStatus: r.factual_review_status, reviewerRole: r.reviewer_role,
  privacyScreeningStatus: r.privacy_screening_status, projectApproval: r.project_approval,
    publicationProfile: r.publication_profile, publicationWarning: r.publication_warning,
    sourceId: r.provenance_source_id, sourceUrl: r.provenance_source_url, provenanceSource: r.provenance_source, sourceRightsStatus: r.source_rights_status,
    retrievedAt: r.provenance_retrieved_at, displayPrecision: r.display_precision, lifecycleStatus: r.lifecycle_status, observationCount: r.observation_count,
  },
};
};
const query = (profile: LocalProfile, filters: LocationFilters, releaseId?: string) => { const params = new URLSearchParams({ profile }); for (const [key, value] of Object.entries(filters)) if (key !== 'category_keys' && value !== undefined && value !== '') params.set(key, String(value)); const categoryKeys = [...new Set(filters.category_keys ?? [])]; if (categoryKeys.length) params.set('category_keys', categoryKeys.join(',')); if (releaseId !== undefined) params.set('release_id', releaseId); return `/api/v2/locations?${params}`; };
// Eligibility is a conservative client-side check, not a publication decision;
// the server's current public projection and suppression rules remain authoritative.
const eligible = (row: WireLocation, profile: LocalProfile, releaseId: string, ruleset: string): boolean =>
  row.publication_profile === profile && row.release_id === releaseId && row.release_ruleset_version === ruleset &&
  row.privacy_screening_status === 'passed' && row.factual_review_status !== 'rejected' &&
  (row.project_approval === 'approved' || (profile === 'community' && row.source_type === 'user_submitted' && row.factual_review_status === 'unreviewed')) &&
  ['cleared', 'attribution_required'].includes(row.source_rights_status);

export class LocalLocationRepository {
  readonly #base: string | undefined;
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, baseUrl?: string) { this.#base = localOrigin(baseUrl); }
  private async json(path: string, signal?: AbortSignal) { const init: RequestInit = { cache: 'no-store' }; if (signal) init.signal = signal; const response = await this.fetcher.call(globalThis, `${this.#base ?? ''}${path}`, init); if (!response.ok) { let code: string | undefined; let message = `Local V2 request failed with status ${response.status}.`; try { const payload = await response.json() as { error?: { code?: string; message?: string } }; code = payload.error?.code; message = payload.error?.message ?? message; } catch { /* Keep the status-safe message. */ } const restricted = response.status === 404 || response.status === 410; const kind: ApiError['kind'] = restricted ? 'restricted' : response.status === 429 ? 'rate-limited' : response.status >= 500 ? 'unavailable' : 'http'; throw fail(kind, restricted ? 'This location snapshot is unavailable.' : message, response.status, code); } try { return await response.json(); } catch { throw fail('invalid-contract', 'Local V2 response was not valid JSON.'); } }
  async list(profile: LocalProfile = 'official', filters: LocationFilters = {}, signal?: AbortSignal, releaseId?: string): Promise<LocalListResult> {
    try {
      const b = envelopeSchema.safeParse(await this.json(query(profile, filters, releaseId), signal));
      if (!b.success || b.data.meta.profile !== profile) throw fail('invalid-contract', 'Local V2 list response was rejected.');
      if (b.data.meta.release_id === null && releaseId !== undefined) throw fail('restricted', 'The requested location release is unavailable.');
      if (b.data.meta.release_id === null) throw fail('no-release', b.data.meta.coverage_note);
      const { release_id, ruleset_version } = b.data.meta;
      if (releaseId !== undefined && release_id !== releaseId) throw fail('restricted', 'The requested location release is unavailable.');
      if (ruleset_version === undefined || b.data.data.some(row => !eligible(row, profile, release_id, ruleset_version))) throw fail('invalid-contract', 'Local V2 list snapshot was rejected.');
      return { locations: b.data.data.map(mapWireLocation), releaseId: release_id, profile, coverageNote: b.data.meta.coverage_note, coverageScope: b.data.meta.coverage_scope ?? 'selected promoted release public facilities', countSemantics: b.data.meta.count_semantics ?? 'Eligible public facility projection rows, not animals or a story-wide total.', nextCursor: b.data.meta.next_cursor ?? null, ruleset: ruleset_version };
    } catch (e) { if (e && typeof e === 'object' && 'kind' in e) throw e; if (e instanceof DOMException && e.name === 'AbortError') throw fail('aborted', 'Local V2 request was aborted.'); if (e instanceof TypeError) throw fail('network', 'Local V2 request could not connect.'); throw fail('invalid-contract', 'Local V2 response could not be read safely.'); }
  }
  async detail(id: string, profile: LocalProfile = 'official', signal?: AbortSignal, releaseId?: string) {
    try {
      const params = new URLSearchParams({ profile }); if (releaseId !== undefined) params.set('release_id', releaseId);
      const b = detailEnvelopeSchema.safeParse(await this.json(`/api/v2/locations/${encodeURIComponent(id)}?${params}`, signal));
      if (!b.success || b.data.meta.profile !== profile || (releaseId !== undefined && b.data.meta.release_id !== releaseId) || !eligible(b.data.data, profile, b.data.meta.release_id, b.data.meta.ruleset_version) || b.data.data.facility_id !== id) throw fail(releaseId !== undefined && b.success && b.data.meta.release_id !== releaseId ? 'restricted' : 'invalid-contract', 'Local V2 detail response was rejected.');
      return { location: mapWireLocation(b.data.data), releaseId: b.data.meta.release_id, profile };
    } catch (e) { if (e && typeof e === 'object' && 'kind' in e) throw e; if (e instanceof DOMException && e.name === 'AbortError') throw fail('aborted', 'Local V2 request was aborted.'); if (e instanceof TypeError) throw fail('network', 'Local V2 request could not connect.'); throw fail('invalid-contract', 'Local V2 response could not be read safely.'); }
  }
}
