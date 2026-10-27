import { FacetsRepository, type FacetResponse } from '../api/FacetsRepository';
import { PublicReleaseRepository } from '../api/PublicReleaseRepository';
import type { TaxonomyPrimaryKey } from '../domain/taxonomy';

export type LandingReleaseSummary = Readonly<{ releaseId: string; records: number; mapped: number; sources: number; countries: number | null }>;
const precisions = new Set(['exact', 'source_reported', 'approximate', 'city', 'coarse', 'unmapped']);
const mappedPrecisions = new Set(['exact', 'source_reported', 'approximate']);

/** Precision is a complete, mutually exclusive dimension. Country facets are capped;
 * legacy category facets are not the public taxonomy and cannot supply these totals. */
export function landingReleaseSummary(facets: FacetResponse): LandingReleaseSummary {
  const locations = facets.dimensions.display_precision;
  const sources = facets.dimensions.source_id;
  if (!locations || !sources || locations.some(facet => !precisions.has(facet.value)) || sources.some(facet => !facet.value.trim())
    || new Set(locations.map(facet => facet.value)).size !== locations.length
    || new Set(sources.map(facet => facet.value)).size !== sources.length) throw new Error('Incomplete release totals');
  const records = locations.reduce((sum, facet) => sum + facet.count, 0);
  const sourceRecords = sources.reduce((sum, facet) => sum + facet.count, 0);
  if (!Number.isSafeInteger(records) || records !== sourceRecords) throw new Error('Inconsistent release totals');
  return { releaseId: facets.releaseId, records,
    mapped: locations.filter(facet => mappedPrecisions.has(facet.value)).reduce((sum, facet) => sum + facet.count, 0),
    sources: sources.filter(facet => facet.count > 0).length, countries: null };
}

/** Country facets are capped. A count is usable only when every mapped precision
 * partition accounts for its entire known record total, without duplicate keys. */
export function mappedCountryCount(facets: FacetResponse, mapped: readonly FacetResponse[]): number | null {
  const expected = new Map((facets.dimensions.display_precision ?? []).filter(facet => mappedPrecisions.has(facet.value) && facet.count > 0).map(facet => [facet.value, facet.count]));
  if(mapped.length !== expected.size) return null;
  const covered = new Set<string>(), countries = new Set<string>();
  for(const partition of mapped) {
    const precision = partition.dimensions.display_precision;
    const rows = partition.dimensions.country_code;
    if(partition.profile !== facets.profile || partition.releaseId !== facets.releaseId || partition.ruleset !== facets.ruleset ||
      !precision || precision.length !== 1 || !rows) return null;
    const key = precision[0]!.value, total = expected.get(key);
    if(total === undefined || covered.has(key) || precision[0]!.count !== total ||
      rows.some(row => !/^[A-Z]{2}$/.test(row.value) || !Number.isSafeInteger(row.count) || row.count < 0) || new Set(rows.map(row => row.value)).size !== rows.length ||
      rows.reduce((sum,row) => sum + row.count,0) !== total) return null;
    covered.add(key);
    for(const row of rows) if(row.count > 0) countries.add(row.value);
  }
  return countries.size;
}

export async function loadLandingReleaseSummary(signal: AbortSignal, releaseId?: string, fetcher: typeof fetch = globalThis.fetch): Promise<LandingReleaseSummary | null> {
  const releases = new PublicReleaseRepository(fetcher);
  const identity = await releases.current('official', signal, releaseId);
  if (!identity) return null;
  const facets = await new FacetsRepository(fetcher).get('official', {}, { releaseId: identity.releaseId }, signal);
  const summary = landingReleaseSummary(facets);
  let countries: number | null = null;
  try {
    const repository = new FacetsRepository(fetcher);
    const mapped = await Promise.all((facets.dimensions.display_precision ?? []).filter(facet => mappedPrecisions.has(facet.value) && facet.count > 0).map(facet => repository.get('official', {display_precision:facet.value}, {releaseId:identity.releaseId,ruleset:facets.ruleset}, signal)));
    countries = mappedCountryCount(facets,mapped);
  } catch(error) { if(signal.aborted) throw error; }
  const checked = await releases.current('official', signal, identity.releaseId);
  if (!checked || checked.releaseId !== identity.releaseId || checked.manifestSha256 !== identity.manifestSha256
    || checked.suppressionGeneration !== identity.suppressionGeneration) throw new Error('Release totals changed');
  return {...summary,countries};
}

export function landingCategoryHref(mapHref: string, releaseId: string, category: TaxonomyPrimaryKey): string {
  const params = new URLSearchParams(mapHref.split('?')[1] ?? '');
  params.delete('selected'); params.delete('cluster'); params.delete('q');
  params.delete('category'); params.set('category', category);
  params.set('release_id', releaseId); params.set('list', 'open');
  return `#/map?${params}`;
}
