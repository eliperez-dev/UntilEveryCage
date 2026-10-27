import { describe, expect, it, vi } from 'vitest';
import type { FacetResponse } from '../../src/api/FacetsRepository';
import { landingCategoryHref, landingReleaseSummary, loadLandingReleaseSummary, mappedCountryCount } from '../../src/app/landingReleaseSummary';

const facets = (dimensions: FacetResponse['dimensions']): FacetResponse => ({ profile: 'official', releaseId: 'synthetic-release', ruleset: 'rules', coverageScope: 'public', countSemantics: 'Records', dimensions });
const dimensions = { display_precision: [{ value: 'source_reported', count: 5 }, { value: 'approximate', count: 2 }, { value: 'city', count: 3 }, { value: 'unmapped', count: 1 }], source_id: [{ value: 'synthetic-a', count: 7 }, { value: 'synthetic-b', count: 4 }] };
const manifest = (generation = 1) => ({ api_version: 'v2', data: { profile: 'official', release_id: 'synthetic-release', manifest: {}, manifest_sha256: 'a'.repeat(64), suppression_generation: generation } });
const response = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
const wireFacets = { api_version: 'v2', meta: { profile: 'official', release_id: 'synthetic-release', ruleset_version: 'rules', release_created_at: '2026-01-01T00:00:00Z', coverage_scope: 'public', count_semantics: 'Records', filters: {} }, dimensions };
const mapped = (precision:string,count:number,countries:readonly {value:string;count:number}[]) => facets({display_precision:[{value:precision,count}],country_code:countries});
const wireMapped = (precision:string,count:number,countries:readonly {value:string;count:number}[]) => ({...wireFacets,meta:{...wireFacets.meta,filters:{display_precision:precision}},dimensions:{display_precision:[{value:precision,count}],country_code:countries}});
const sourceCountries = [{value:'DK',count:4},{value:'US',count:1}], approximateCountries = [{value:'DK',count:2}];

describe('landing release aggregates', () => {
  it('counts the complete precision dimension and excludes locality-only locations from mapped totals', () => {
    expect(landingReleaseSummary(facets({ ...dimensions, country_code: Array.from({ length: 20 }, (_, i) => ({ value: String(i), count: 1 })) }))).toEqual({ releaseId: 'synthetic-release', records: 11, mapped: 7, sources: 2, countries:null });
    expect(landingReleaseSummary(facets({ display_precision: [], source_id: [] }))).toMatchObject({ records: 0, mapped: 0, sources: 0 });
  });
  it('rejects missing, duplicate, inconsistent and unknown dimensions rather than making up totals', () => {
    for (const value of [ {}, { ...dimensions, source_id: [] }, { ...dimensions, display_precision: [...dimensions.display_precision, dimensions.display_precision[0]!] }, { ...dimensions, display_precision: [{ value: 'unsupported', count: 11 }] }, { ...dimensions, source_id: [{ value: 'same', count: 5 }, { value: 'same', count: 6 }] } ]) expect(() => landingReleaseSummary(facets(value))).toThrow();
  });
  it('pins release and revalidates current restriction identity around facets without loading map points', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(response(manifest())).mockResolvedValueOnce(response(wireFacets)).mockResolvedValueOnce(response(wireMapped('source_reported',5,sourceCountries))).mockResolvedValueOnce(response(wireMapped('approximate',2,approximateCountries))).mockResolvedValueOnce(response(manifest()));
    const signal = new AbortController().signal;
    await expect(loadLandingReleaseSummary(signal, 'synthetic-release', fetcher)).resolves.toMatchObject({ records: 11, mapped: 7, sources: 2, countries:2 });
    expect(fetcher.mock.calls.map(call => String(call[0]).split('?')[0])).toEqual(['/api/v2/releases/manifest', '/api/v2/discovery/facets','/api/v2/discovery/facets','/api/v2/discovery/facets', '/api/v2/releases/manifest']);
    for (const call of fetcher.mock.calls) { expect(new URL(String(call[0]), 'https://example.test').searchParams.get('release_id')).toBe('synthetic-release'); expect(call[1]).toMatchObject({ signal, cache: 'no-store' }); }
  });
  it('rejects a restriction change and stops on unavailable release', async () => {
    const changed = vi.fn().mockResolvedValueOnce(response(manifest())).mockResolvedValueOnce(response(wireFacets)).mockResolvedValueOnce(response(wireMapped('source_reported',5,sourceCountries))).mockResolvedValueOnce(response(wireMapped('approximate',2,approximateCountries))).mockResolvedValueOnce(response(manifest(2)));
    await expect(loadLandingReleaseSummary(new AbortController().signal, undefined, changed)).rejects.toThrow('Release totals changed');
    const unavailable = vi.fn().mockResolvedValue(new Response(null, { status: 404 }));
    await expect(loadLandingReleaseSummary(new AbortController().signal, undefined, unavailable)).resolves.toBeNull(); expect(unavailable).toHaveBeenCalledTimes(1);
  });
  it('counts only an exhaustive union of mapped countries, excluding unmapped-only countries',()=>{
    const base=facets({...dimensions,country_code:[...sourceCountries,{value:'FR',count:4}]});
    expect(mappedCountryCount(base,[mapped('source_reported',5,sourceCountries),mapped('approximate',2,approximateCountries)])).toBe(2);
    expect(mappedCountryCount(facets({display_precision:[{value:'unmapped',count:5}],source_id:[{value:'synthetic',count:5}]}),[])).toBe(0);
  });
  it('cannot turn capped, missing, duplicate, foreign or inconsistent country partitions into a count',()=>{
    const base=facets(dimensions), good=mapped('approximate',2,approximateCountries);
    for(const bad of [mapped('source_reported',5,[{value:'DK',count:4}]),mapped('source_reported',5,[{value:'DK',count:3},{value:'DK',count:2}]),mapped('source_reported',5,[{value:'unknown',count:5}]),{...mapped('source_reported',5,sourceCountries),releaseId:'other'},mapped('exact',5,sourceCountries)])expect(mappedCountryCount(base,[bad,good])).toBeNull();
    expect(mappedCountryCount(base,[good])).toBeNull();expect(mappedCountryCount(base,[good,good])).toBeNull();
  });
  it('keeps the other release totals if a country request fails',async()=>{
    const fetcher=vi.fn().mockResolvedValueOnce(response(manifest())).mockResolvedValueOnce(response(wireFacets)).mockResolvedValueOnce(new Response(null,{status:503})).mockResolvedValueOnce(response(wireMapped('approximate',2,approximateCountries))).mockResolvedValueOnce(response(manifest()));
    await expect(loadLandingReleaseSummary(new AbortController().signal,undefined,fetcher)).resolves.toMatchObject({records:11,mapped:7,sources:2,countries:null});
  });
  it('category links preserve release and public camera while removing stale selection and search text', () => {
    const url = landingCategoryHref('#/map?lat=12&lon=3&z=5&category=slaughter&selected=synthetic&q=private&release_id=old', 'synthetic-release', 'processing_and_preparation');
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('release_id')).toBe('synthetic-release'); expect(params.get('list')).toBe('open'); expect(params.getAll('category')).toEqual(['processing_and_preparation']); expect(params.get('lat')).toBe('12'); expect(params.has('selected')).toBe(false); expect(params.has('q')).toBe(false);
  });
});
