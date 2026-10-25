import { describe, expect, it, vi } from 'vitest';
import { createApplicationVersionRepository, parseApplicationVersion } from '../../src/api/ApplicationVersionRepository';

describe('application version', () => {
  it('accepts a semantic version and rejects missing or malformed data', () => {
    expect(parseApplicationVersion({ application_version: '2.0.0' })).toEqual({ version: '2.0.0' });
    expect(parseApplicationVersion({ application_version: 'not-known' })).toBeNull();
    expect(parseApplicationVersion({})).toBeNull();
  });

  it('fetches liveness once even when the footer requests concurrently', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ status: 'ok', service: 'uec-api', application_version: '2.0.0' })));
    const repository = createApplicationVersionRepository(fetcher);
    await expect(Promise.all([repository.current(), repository.current()])).resolves.toEqual([{ version: '2.0.0' }, { version: '2.0.0' }]);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith('/health/live', { headers: { Accept: 'application/json' } });
  });

  it('fails quietly for unavailable health metadata', async () => {
    const repository = createApplicationVersionRepository(async () => new Response('', { status: 503 }));
    await expect(repository.current()).resolves.toBeNull();
  });
});
