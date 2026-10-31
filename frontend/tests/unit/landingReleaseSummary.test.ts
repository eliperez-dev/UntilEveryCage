import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FacetResponse } from '../../src/api/FacetsRepository';
import { landingCategoryHref, landingReleaseSummary, loadLandingReleaseSummary, mappedCountryCount } from '../../src/app/landingReleaseSummary';
import { LANDING_SUMMARY_CACHE_KEY, LANDING_SUMMARY_CACHE_TTL_MS, type LandingSummaryStorage } from '../../src/app/landingSummaryCache';

const facets = (dimensions: FacetResponse['dimensions']): FacetResponse => ({ profile: 'official', releaseId: 'synthetic-release', ruleset: 'rules', coverageScope: 'public', countSemantics: 'Records', dimensions });
const dimensions = { display_precision: [{ value: 'source_reported', count: 5 }, { value: 'approximate', count: 2 }, { value: 'city', count: 3 }, { value: 'unmapped', count: 1 }], source_id: [{ value: 'synthetic-a', count: 7 }, { value: 'synthetic-b', count: 4 }] };
const manifest = (generation = 1) => ({ api_version: 'v2', data: { profile: 'official', release_id: 'synthetic-release', manifest: {}, manifest_sha256: 'a'.repeat(64), suppression_generation: generation } });
const response = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
const wireFacets = { api_version: 'v2', meta: { profile: 'official', release_id: 'synthetic-release', ruleset_version: 'rules', release_created_at: '2026-01-01T00:00:00Z', coverage_scope: 'public', count_semantics: 'Records', filters: {} }, dimensions };
const mapped = (precision:string,count:number,countries:readonly {value:string;count:number}[]) => facets({display_precision:[{value:precision,count}],country_code:countries});
const wireMapped = (precision:string,count:number,countries:readonly {value:string;count:number}[]) => ({...wireFacets,meta:{...wireFacets.meta,filters:{display_precision:precision}},dimensions:{display_precision:[{value:precision,count}],country_code:countries}});
const sourceCountries = [{value:'DK',count:4},{value:'US',count:1}], approximateCountries = [{value:'DK',count:2}];
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
};
const aggregateFetcher = (handler?: (url: URL) => Promise<Response> | undefined) => vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
  const url = new URL(String(input), 'https://example.test');
  const intercepted = handler?.(url);
  if (intercepted) return intercepted;
  if (url.pathname === '/api/v2/releases/manifest') return Promise.resolve(response(manifest()));
  const precision = url.searchParams.get('display_precision');
  return Promise.resolve(response(precision ? wireMapped(precision, precision === 'approximate' ? 2 : 5, precision === 'approximate' ? approximateCountries : sourceCountries) : wireFacets));
});

describe('landing release aggregates', () => {
  beforeEach(() => localStorage.clear());
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
  it('finishes the authoritative initial manifest before starting any live facets', async () => {
    const firstManifest = deferred<Response>();
    const fetcher = aggregateFetcher(url => !url.searchParams.has('release_id') ? firstManifest.promise : undefined);
    const loading = loadLandingReleaseSummary(new AbortController().signal, undefined, fetcher);
    expect(fetcher.mock.calls).toHaveLength(1);
    expect(String(fetcher.mock.calls[0]![0])).toContain('/releases/manifest');
    firstManifest.resolve(response(manifest()));
    await expect(loading).resolves.toMatchObject({ records: 11, countries: 2 });
    for (const [input] of fetcher.mock.calls.slice(1)) expect(new URL(String(input), 'https://example.test').searchParams.get('release_id')).toBe('synthetic-release');
  });
  it('publishes checked totals while country partitions are still pending, then checks countries separately', async () => {
    const country = deferred<Response>(), totals = deferred<void>();
    const initialCheck = deferred<Response>(); let checks = 0;
    const fetcher = aggregateFetcher(url => {
      if (url.pathname.endsWith('/manifest') && ++checks === 2) return initialCheck.promise;
      if (url.searchParams.get('display_precision') === 'source_reported') return country.promise;
      return undefined;
    });
    const progress = vi.fn(() => totals.resolve());
    const loading = loadLandingReleaseSummary(new AbortController().signal, undefined, fetcher, progress);
    await vi.waitFor(() => expect(checks).toBe(2));
    expect(progress).not.toHaveBeenCalled();
    expect(fetcher.mock.calls.some(([input]) => new URL(String(input), 'https://example.test').searchParams.has('display_precision'))).toBe(false);
    initialCheck.resolve(response(manifest())); await totals.promise;
    expect(progress).toHaveBeenCalledWith({ releaseId: 'synthetic-release', records: 11, mapped: 7, sources: 2, countries: null });
    country.resolve(response(wireMapped('source_reported', 5, sourceCountries)));
    await expect(loading).resolves.toMatchObject({ countries: 2 });
    expect(checks).toBe(3);
    expect(fetcher.mock.calls.every(([input]) => ['/api/v2/releases/manifest', '/api/v2/discovery/facets'].includes(new URL(String(input), 'https://example.test').pathname))).toBe(true);
  });
  it('does not publish initial totals if their closing restriction check fails', async () => {
    let checks = 0;
    const fetcher = aggregateFetcher(url => url.pathname.endsWith('/manifest') && ++checks === 2 ? Promise.resolve(response(manifest(2))) : undefined);
    const progress = vi.fn();
    await expect(loadLandingReleaseSummary(new AbortController().signal, undefined, fetcher, progress)).rejects.toThrow('Release totals changed');
    expect(progress).not.toHaveBeenCalled();
  });
  it('rejects a later restriction change after the progressive totals were shown', async () => {
    const country = deferred<Response>(), totals = deferred<void>(); let checks = 0;
    const fetcher = aggregateFetcher(url => {
      if (url.pathname.endsWith('/manifest') && ++checks === 3) return Promise.resolve(response(manifest(2)));
      return url.searchParams.get('display_precision') === 'source_reported' ? country.promise : undefined;
    });
    const loading = loadLandingReleaseSummary(new AbortController().signal, undefined, fetcher, () => totals.resolve());
    const rejected = expect(loading).rejects.toThrow('Release totals changed');
    await totals.promise; country.resolve(response(wireMapped('source_reported', 5, sourceCountries)));
    await rejected;
  });
  it('rejects a facet response that does not belong to the manifest-pinned release', async () => {
    const fetcher = aggregateFetcher(url => url.pathname.endsWith('/facets')
      ? Promise.resolve(response({ ...wireFacets, meta: { ...wireFacets.meta, release_id: 'other-release' } })) : undefined);
    const progress = vi.fn();
    await expect(loadLandingReleaseSummary(new AbortController().signal, undefined, fetcher, progress)).rejects.toThrow('different profile or promoted release');
    expect(fetcher).toHaveBeenCalledTimes(2); expect(progress).not.toHaveBeenCalled();
  });
  it('suppresses progress and final results after cancellation even if a fetcher ignores the signal', async () => {
    const firstFacets = deferred<Response>(), controller = new AbortController();
    const fetcher = aggregateFetcher(url => url.pathname.endsWith('/facets') ? firstFacets.promise : undefined);
    const progress = vi.fn();
    const loading = loadLandingReleaseSummary(controller.signal, undefined, fetcher, progress);
    const rejected = expect(loading).rejects.toMatchObject({ name: 'AbortError' });
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    controller.abort(); firstFacets.resolve(response(wireFacets)); await rejected;
    expect(progress).not.toHaveBeenCalled();
    expect(fetcher.mock.calls).toHaveLength(2);
  });
  it('does not publish countries after cancellation while their requests are pending', async () => {
    const country = deferred<Response>(), totals = deferred<void>(), controller = new AbortController();
    const fetcher = aggregateFetcher(url => url.searchParams.get('display_precision') === 'source_reported' ? country.promise : undefined);
    const progress = vi.fn(() => totals.resolve());
    const loading = loadLandingReleaseSummary(controller.signal, undefined, fetcher, progress);
    const rejected = expect(loading).rejects.toMatchObject({ name: 'AbortError' });
    await totals.promise; controller.abort(); country.resolve(response(wireMapped('source_reported', 5, sourceCountries)));
    await rejected;
    expect(progress).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls.filter(([input]) => new URL(String(input), 'https://example.test').pathname.endsWith('/manifest'))).toHaveLength(2);
    expect(localStorage.getItem(LANDING_SUMMARY_CACHE_KEY)).toBeNull();
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

describe('validated persisted landing aggregates', () => {
  beforeEach(() => localStorage.clear());
  const complete = { releaseId: 'synthetic-release', records: 11, mapped: 7, sources: 2, countries: 2 };
  const saved = () => ({ version: 1, profile: 'official', savedAt: 1000, identity: { releaseId: 'synthetic-release', manifestSha256: 'a'.repeat(64), suppressionGeneration: 1 }, summary: complete });
  const seed = (value: unknown = saved()) => localStorage.setItem(LANDING_SUMMARY_CACHE_KEY, JSON.stringify(value));
  const options = { now: () => 2000 };

  it('persists only complete checked totals and a warm reload uses one fresh no-store manifest', async () => {
    const cold = aggregateFetcher(); const progress = vi.fn();
    await expect(loadLandingReleaseSummary(signal(), undefined, cold, progress, options)).resolves.toEqual(complete);
    expect(cold.mock.calls.filter(([input]) => String(input).includes('/manifest'))).toHaveLength(3);
    const entry = localStorage.getItem(LANDING_SUMMARY_CACHE_KEY)!;
    expect(entry.length).toBeLessThan(2048); expect(JSON.parse(entry)).toMatchObject({ version: 1, profile: 'official', summary: complete });
    const warm = aggregateFetcher(), warmProgress = vi.fn();
    await expect(loadLandingReleaseSummary(signal(), undefined, warm, warmProgress, options)).resolves.toEqual(complete);
    expect(warm.mock.calls).toHaveLength(1); expect(String(warm.mock.calls[0]![0])).toContain('/api/v2/releases/manifest');
    expect(warm.mock.calls[0]![1]).toMatchObject({ cache: 'no-store', credentials: 'omit' });
    expect(warmProgress).not.toHaveBeenCalled(); expect(localStorage.getItem(LANDING_SUMMARY_CACHE_KEY)).toBe(entry);
  });
  it('waits for manifest eligibility before returning a stored count, even when transport ignores abort', async () => {
    seed(); const manifestReply = deferred<Response>(), controller = new AbortController(), progress = vi.fn();
    const fetcher = aggregateFetcher(() => manifestReply.promise);
    const loading = loadLandingReleaseSummary(controller.signal, undefined, fetcher, progress, options);
    expect(fetcher).toHaveBeenCalledTimes(1); expect(progress).not.toHaveBeenCalled();
    const rejected = expect(loading).rejects.toMatchObject({ name: 'AbortError' });
    controller.abort(); manifestReply.resolve(response(manifest())); await rejected;
    expect(progress).not.toHaveBeenCalled(); expect(localStorage.getItem(LANDING_SUMMARY_CACHE_KEY)).toBeNull();
  });
  it('clears cached counts on missing or failed manifest checks without an offline fallback', async () => {
    for (const result of [new Response(null, { status: 404 }), new Response(null, { status: 503 })]) {
      seed(); const fetcher = vi.fn(async () => result), progress = vi.fn();
      if (result.status === 404) await expect(loadLandingReleaseSummary(signal(), undefined, fetcher, progress, options)).resolves.toBeNull();
      else await expect(loadLandingReleaseSummary(signal(), undefined, fetcher, progress, options)).rejects.toThrow();
      expect(fetcher).toHaveBeenCalledTimes(1); expect(progress).not.toHaveBeenCalled(); expect(localStorage.getItem(LANDING_SUMMARY_CACHE_KEY)).toBeNull();
    }
  });
  it('clears a changed restriction or manifest identity before fetching new aggregates', async () => {
    for (const identity of [manifest(2), { ...manifest(), data: { ...manifest().data, manifest_sha256: 'b'.repeat(64) } }]) {
      seed(); const held = deferred<Response>(); let removedBeforeFacets = false;
      const fetcher = aggregateFetcher(url => url.pathname.endsWith('/manifest') ? Promise.resolve(response(identity)) : (removedBeforeFacets = localStorage.getItem(LANDING_SUMMARY_CACHE_KEY) === null, held.promise));
      const controller = new AbortController(), progress = vi.fn();
      const loading = loadLandingReleaseSummary(controller.signal, undefined, fetcher, progress, options);
      const rejected = expect(loading).rejects.toMatchObject({ name: 'AbortError' });
      await vi.waitFor(() => expect(removedBeforeFacets).toBe(true)); expect(progress).not.toHaveBeenCalled();
      controller.abort(); held.resolve(response(wireFacets)); await rejected;
      expect(localStorage.getItem(LANDING_SUMMARY_CACHE_KEY)).toBeNull();
    }
  });
  it('never returns cached totals for a different current or explicitly selected release', async () => {
    for (const requested of [undefined, 'new-release']) {
      seed(); const nextManifest = { ...manifest(), data: { ...manifest().data, release_id: 'new-release' } };
      const fetcher = aggregateFetcher(url => url.pathname.endsWith('/manifest') ? Promise.resolve(response(nextManifest)) : Promise.resolve(new Response(null, { status: 503 })));
      const progress = vi.fn();
      await expect(loadLandingReleaseSummary(signal(), requested, fetcher, progress, options)).rejects.toThrow();
      expect(progress).not.toHaveBeenCalled(); expect(localStorage.getItem(LANDING_SUMMARY_CACHE_KEY)).toBeNull();
    }
  });
  it('rejects corrupt, oversized, expired, future, extra-field and inconsistent entries', async () => {
    const invalid = ['{', 'x'.repeat(2049), ...[
      { ...saved(), version: 2 }, { ...saved(), profile: 'community' }, { ...saved(), savedAt: 2001 },
      { ...saved(), savedAt: 2000 - LANDING_SUMMARY_CACHE_TTL_MS }, { ...saved(), privateRows: [] },
      { ...saved(), summary: { ...complete, records: Number.MAX_SAFE_INTEGER + 1 } },
      { ...saved(), summary: { ...complete, mapped: 12 } }, { ...saved(), summary: { ...complete, countries: 8 } },
      { ...saved(), summary: { ...complete, sources: 0 } }, { ...saved(), summary: { ...complete, countries: 0 } },
      { ...saved(), summary: { ...complete, countries: null } }, { ...saved(), summary: { ...complete, sourceRows: [] } },
      { ...saved(), identity: { ...saved().identity, suppressionGeneration: -1 } },
      { ...saved(), identity: { ...saved().identity, releaseId: 'other-release' } },
    ].map(value => JSON.stringify(value))];
    for (const value of invalid) {
      localStorage.setItem(LANDING_SUMMARY_CACHE_KEY, value);
      const fetcher = aggregateFetcher();
      await expect(loadLandingReleaseSummary(signal(), undefined, fetcher, undefined, options)).resolves.toEqual(complete);
      expect(fetcher.mock.calls).toHaveLength(5);
    }
  });
  it('continues with live totals when storage is unavailable or throws', async () => {
    const blocked: LandingSummaryStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('quota'); }, removeItem() { throw new Error('blocked'); } };
    for (const storage of [null, blocked]) {
      const fetcher = aggregateFetcher();
      await expect(loadLandingReleaseSummary(signal(), undefined, fetcher, undefined, { ...options, storage })).resolves.toEqual(complete);
      expect(fetcher.mock.calls).toHaveLength(5);
    }
  });
  it('expires an otherwise valid entry exactly at the24hour boundary', async () => {
    seed(); const fetcher = aggregateFetcher();
    await expect(loadLandingReleaseSummary(signal(), undefined, fetcher, undefined, { now: () => 1000 + LANDING_SUMMARY_CACHE_TTL_MS })).resolves.toEqual(complete);
    expect(fetcher.mock.calls).toHaveLength(5);
  });
  it('does not cache partial countries or changed closing identities', async () => {
    const failedCountry = aggregateFetcher(url => url.searchParams.has('display_precision') ? Promise.resolve(new Response(null, { status: 503 })) : undefined);
    await expect(loadLandingReleaseSummary(signal(), undefined, failedCountry, undefined, options)).resolves.toMatchObject({ countries: null });
    expect(localStorage.getItem(LANDING_SUMMARY_CACHE_KEY)).toBeNull();
    let checks = 0;
    const changed = aggregateFetcher(url => url.pathname.endsWith('/manifest') ? Promise.resolve(response(manifest(++checks === 3 ? 2 : 1))) : undefined);
    await expect(loadLandingReleaseSummary(signal(), undefined, changed, vi.fn(), options)).rejects.toThrow('Release totals changed');
    expect(localStorage.getItem(LANDING_SUMMARY_CACHE_KEY)).toBeNull();
  });
});

function signal() { return new AbortController().signal; }
