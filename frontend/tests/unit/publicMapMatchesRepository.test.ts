import { describe, expect, it } from 'vitest';
import { PublicMapMatchesRepository } from '../../src/api/PublicMapMatchesRepository';

const id = '550e8400-e29b-41d4-a716-446655440000';
const identity = { releaseId: 'synthetic-match-release', manifestSha256: 'a'.repeat(64), suppressionGeneration: 4 };
const payload = () => ({ api_version: 'v2', data: { facility_ids: [id] }, meta: { profile: 'official', release_id: identity.releaseId, manifest_sha256: identity.manifestSha256, suppression_generation: identity.suppressionGeneration, total_count: 2, mapped_count: 1 } });

describe('public map matching repository', () => {
  it('requests all matching IDs once with list predicates, no pagination, no storage cache', async () => {
    let requestUrl = ''; let requestInit: RequestInit | undefined;
    const controller = new AbortController();
    const repository = new PublicMapMatchesRepository(async (url, init) => { requestUrl = String(url); requestInit = init; return new Response(JSON.stringify(payload())); });
    expect(await repository.get({ q: 'synthetic query', category_keys: ['slaughter'], country_code: 'ES,FR', source_id: 'synthetic-source', display_precision: 'city', latitude: 40, longitude: -3, radius_km: 25, limit: 100, cursor: 'ignored' }, identity, controller.signal)).toEqual({ facilityIds: [id], totalCount: 2, mappedCount: 1 });
    const url = new URL(requestUrl, 'https://example.test');
    expect(url.pathname).toBe('/api/v2/map/matches');
    expect(Object.fromEntries(url.searchParams)).toEqual({ profile: 'official', release_id: identity.releaseId, q: 'synthetic query', category_keys: 'slaughter', country_code: 'ES,FR', source_id: 'synthetic-source', display_precision: 'city', latitude: '40', longitude: '-3', radius_km: '25' });
    expect(requestInit).toMatchObject({ cache: 'no-store', credentials: 'omit', signal: controller.signal });
  });

  it.each(['release_id', 'manifest_sha256', 'suppression_generation'] as const)('rejects mismatched %s rather than accepting stale facility IDs', async field => {
    const body = payload();
    Object.assign(body.meta, { [field]: field === 'suppression_generation' ? 3 : field === 'manifest_sha256' ? 'b'.repeat(64) : 'another-release' });
    const repository = new PublicMapMatchesRepository(async () => new Response(JSON.stringify(body)));
    await expect(repository.get({}, identity)).rejects.toThrow('different release');
  });

  it('rejects duplicate IDs, inconsistent counts, private extras and malformed IDs', async () => {
    const bodies = [
      { ...payload(), data: { facility_ids: [id, id] }, meta: { ...payload().meta, mapped_count: 2 } },
      { ...payload(), meta: { ...payload().meta, mapped_count: 3 } },
      { ...payload(), data: { facility_ids: [id], address: 'synthetic forbidden extra' } },
      { ...payload(), data: { facility_ids: ['not-an-id'] } },
    ];
    for (const body of bodies) {
      const repository = new PublicMapMatchesRepository(async () => new Response(JSON.stringify(body)));
      await expect(repository.get({}, identity)).rejects.toThrow();
    }
  });

  it('passes cancellation through and never surfaces query text from server errors', async () => {
    const controller = new AbortController(); controller.abort();
    const abort = new DOMException('cancelled', 'AbortError');
    const aborted = new PublicMapMatchesRepository(async () => { throw abort; });
    await expect(aborted.get({}, identity, controller.signal)).rejects.toBe(abort);
    const unavailable = new PublicMapMatchesRepository(async () => new Response('sensitive query server message', { status: 500 }));
    await expect(unavailable.get({ q: 'sensitive query' }, identity)).rejects.toThrow('Matching map locations could not be loaded. Try again.');
  });
});
