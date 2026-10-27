import { FacetsRepository, type FacetResponse } from '../api/FacetsRepository';
import { PublicReleaseRepository } from '../api/PublicReleaseRepository';
import type { TaxonomyPrimaryKey } from '../domain/taxonomy';

export type LandingReleaseSummary = Readonly<{ releaseId: string; records: number; mapped: number; sources: number }>;
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
    sources: sources.filter(facet => facet.count > 0).length };
}

export async function loadLandingReleaseSummary(signal: AbortSignal, releaseId?: string, fetcher: typeof fetch = globalThis.fetch): Promise<LandingReleaseSummary | null> {
  const releases = new PublicReleaseRepository(fetcher);
  const identity = await releases.current('official', signal, releaseId);
  if (!identity) return null;
  const facets = await new FacetsRepository(fetcher).get('official', {}, { releaseId: identity.releaseId }, signal);
  const checked = await releases.current('official', signal, identity.releaseId);
  if (!checked || checked.releaseId !== identity.releaseId || checked.manifestSha256 !== identity.manifestSha256
    || checked.suppressionGeneration !== identity.suppressionGeneration) throw new Error('Release totals changed');
  return landingReleaseSummary(facets);
}

export function landingCategoryHref(mapHref: string, releaseId: string, category: TaxonomyPrimaryKey): string {
  const params = new URLSearchParams(mapHref.split('?')[1] ?? '');
  params.delete('selected'); params.delete('cluster'); params.delete('q');
  params.delete('category'); params.set('category', category);
  params.set('release_id', releaseId); params.set('list', 'open');
  return `#/map?${params}`;
}
