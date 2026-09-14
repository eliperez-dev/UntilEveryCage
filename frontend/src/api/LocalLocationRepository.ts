import { detailEnvelopeSchema, envelopeSchema, type WireLocation } from './wireSchema';
import type { ApiError } from './errors';
import type { Location } from '../domain/location';

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export type LocalProfile = 'official' | 'secondary' | 'community';
export type LocationFilters = Readonly<{ country_code?: string | undefined; category?: string | undefined; source_type?: string | undefined; display_precision?: string | undefined; lifecycle_status?: string | undefined; cursor?: string | undefined }>;
export type LocalListResult = Readonly<{ locations: readonly Location[]; releaseId: string; profile: LocalProfile; coverageNote: string; nextCursor: string | null; ruleset?: string }>;
export const localOrigin = (value: string | undefined): string | undefined => { if (!value) return undefined; const url = new URL(value); if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '::1'].includes(url.hostname)) throw new Error('Local API origin must be loopback HTTP.'); return url.origin; };
const fail = (kind: ApiError['kind'], message: string, status?: number): ApiError => Object.assign(new Error(message), status === undefined ? { kind } : { kind, status });
const map = (r: WireLocation): Location => ({
  id: r.facility_id, name: r.canonical_name, region: r.city ?? r.country_code, category: r.category,
  lat: r.latitude, lon: r.longitude, observed: r.last_observed_at ?? r.first_observed_at ?? 'unknown', source: r.provenance_source_name,
  evidence: {
    sourceType: r.source_type, factualReviewStatus: r.factual_review_status, reviewerRole: r.reviewer_role,
    privacyScreeningStatus: r.privacy_screening_status, projectApproval: r.project_approval,
    publicationProfile: r.publication_profile, publicationWarning: r.publication_warning,
    sourceId: r.provenance_source_id, sourceUrl: r.provenance_source_url,
    retrievedAt: r.provenance_retrieved_at, displayPrecision: r.display_precision,
  },
});
const query = (profile: LocalProfile, filters: LocationFilters) => { const params = new URLSearchParams({ profile }); for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value); return `/api/v2/locations?${params}`; };
const eligible = (row: WireLocation, profile: LocalProfile, releaseId: string, ruleset: string): boolean =>
  row.publication_profile === profile && row.release_id === releaseId && row.release_ruleset_version === ruleset &&
  row.privacy_screening_status === 'passed' && row.factual_review_status !== 'rejected' &&
  (row.project_approval === 'approved' || (profile === 'community' && row.source_type === 'user_submitted' && row.factual_review_status === 'unreviewed'));

export class LocalLocationRepository {
  readonly #base: string | undefined;
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, baseUrl?: string) { this.#base = localOrigin(baseUrl); }
  private async json(path: string, signal?: AbortSignal) { const init: RequestInit = { cache: 'no-store' }; if (signal) init.signal = signal; const response = await this.fetcher.call(globalThis, `${this.#base ?? ''}${path}`, init); if (!response.ok) throw fail('http', `Local V2 request failed with status ${response.status}`, response.status); try { return await response.json(); } catch { throw fail('invalid-contract', 'Local V2 response was not valid JSON.'); } }
  async list(profile: LocalProfile = 'official', filters: LocationFilters = {}, signal?: AbortSignal): Promise<LocalListResult> {
    try {
      const b = envelopeSchema.safeParse(await this.json(query(profile, filters), signal));
      if (!b.success || b.data.meta.profile !== profile) throw fail('invalid-contract', 'Local V2 list response was rejected.');
      if (b.data.meta.release_id === null) throw fail('no-release', b.data.meta.coverage_note);
      const { release_id, ruleset_version } = b.data.meta;
      if (ruleset_version === undefined || b.data.data.some(row => !eligible(row, profile, release_id, ruleset_version))) throw fail('invalid-contract', 'Local V2 list snapshot was rejected.');
      return { locations: b.data.data.map(map), releaseId: release_id, profile, coverageNote: b.data.meta.coverage_note, nextCursor: b.data.meta.next_cursor ?? null, ruleset: ruleset_version };
    } catch (e) { if (e && typeof e === 'object' && 'kind' in e) throw e; if (e instanceof DOMException && e.name === 'AbortError') throw fail('aborted', 'Local V2 request was aborted.'); if (e instanceof TypeError) throw fail('network', 'Local V2 request could not connect.'); throw fail('invalid-contract', 'Local V2 response could not be read safely.'); }
  }
  async detail(id: string, profile: LocalProfile = 'official', signal?: AbortSignal) {
    try {
      const b = detailEnvelopeSchema.safeParse(await this.json(`/api/v2/locations/${encodeURIComponent(id)}?profile=${profile}`, signal));
      if (!b.success || b.data.meta.profile !== profile || !eligible(b.data.data, profile, b.data.meta.release_id, b.data.meta.ruleset_version) || b.data.data.facility_id !== id) throw fail('invalid-contract', 'Local V2 detail response was rejected.');
      return { location: map(b.data.data), releaseId: b.data.meta.release_id, profile };
    } catch (e) { if (e && typeof e === 'object' && 'kind' in e) throw e; if (e instanceof DOMException && e.name === 'AbortError') throw fail('aborted', 'Local V2 request was aborted.'); if (e instanceof TypeError) throw fail('network', 'Local V2 request could not connect.'); throw fail('invalid-contract', 'Local V2 response could not be read safely.'); }
  }
}
