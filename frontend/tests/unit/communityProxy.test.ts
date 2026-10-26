// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';
import config from '../../vite.config';
import type { ProxyOptions, UserConfig } from 'vite';

afterEach(() => vi.unstubAllEnvs());

async function configuredProxy(override: string | undefined) {
  vi.stubEnv('UEC_COMMUNITY_API_ORIGIN', override);
  vi.stubEnv('VITE_API_ORIGIN', 'http://127.0.0.1:8000');
  if (typeof config !== 'function') throw new Error('Expected configurable Vite setup');
  return await config({ command: 'serve', mode: 'test' }) as UserConfig;
}
function destination(proxy: Record<string, string | ProxyOptions> | undefined, path: string) {
  const key = Object.keys(proxy ?? {}).find(prefix => path.startsWith(prefix));
  const entry = key ? proxy?.[key] : undefined;
  return typeof entry === 'string' ? entry : entry?.target;
}

describe('split contribution-service routing', () => {
  it('isolates the explicit local secure proxy ahead of normal contribution and data requests', async () => {
    vi.stubEnv('VITE_SECURE_INBOX_EXPERIMENT', 'true');
    vi.stubEnv('UEC_SECURE_COMMUNITY_API_ORIGIN', 'http://127.0.0.1:58324');
    const settings = await configuredProxy('https://contributions.example.test');
    expect(destination(settings.server?.proxy, '/api/community/secure/inbox')).toBe('http://127.0.0.1:58324');
    expect(destination(settings.server?.proxy, '/api/private/community/secure/queue')).toBe('http://127.0.0.1:58324');
    expect(destination(settings.server?.proxy, '/api/community/submissions')).toBe('https://contributions.example.test');
    expect(destination(settings.server?.proxy, '/api/v2/locations')).toBe('http://127.0.0.1:8000');
    expect(JSON.stringify(settings.define)).not.toContain('58324');
  });
  it('does not enable the secure override without the explicit flag or during build', async () => {
    vi.stubEnv('UEC_SECURE_COMMUNITY_API_ORIGIN', 'http://127.0.0.1:58324');
    vi.stubEnv('VITE_SECURE_INBOX_EXPERIMENT', 'false');
    let settings = await configuredProxy(undefined);
    expect(destination(settings.server?.proxy, '/api/community/secure/inbox')).toBe('http://127.0.0.1:8000');
    vi.stubEnv('VITE_SECURE_INBOX_EXPERIMENT', 'true');
    if (typeof config !== 'function') throw new Error();
    settings = await config({ command: 'build', mode: 'production' }) as UserConfig;
    expect(destination(settings.server?.proxy, '/api/community/secure/inbox')).toBe('http://127.0.0.1:8000');
  });
  it('rejects external, credentialed or path-bearing secure proxy origins', async () => {
    vi.stubEnv('VITE_SECURE_INBOX_EXPERIMENT', 'true');
    for (const value of ['https://example.test', 'http://user:password@127.0.0.1:58324', 'http://127.0.0.1:58324/private', 'http://127.0.0.1:58324/?token=x']) {
      vi.stubEnv('UEC_SECURE_COMMUNITY_API_ORIGIN', value);
      await expect(configuredProxy(undefined)).rejects.toThrow('loopback API origin');
    }
  });
  it('routes intake, status and authenticated review to the same service in dev and preview', async () => {
    const settings = await configuredProxy('https://contributions.example.test');
    for (const proxy of [settings.server?.proxy, settings.preview?.proxy]) {
      for (const path of ['/api/community/submissions', '/api/community/status', '/api/private/community/submissions?limit=50', '/api/private/community/submissions/synthetic/disposition']) {
        expect(destination(proxy, path)).toBe('https://contributions.example.test');
      }
      expect(destination(proxy, '/api/v2/locations')).toBe('http://127.0.0.1:8000');
    }
    expect(JSON.stringify(settings.define)).not.toContain('contributions.example.test');
  });
  it('keeps all contribution requests on the normal API when no override is configured', async () => {
    const settings = await configuredProxy(undefined);
    for (const proxy of [settings.server?.proxy, settings.preview?.proxy]) {
      expect(destination(proxy, '/api/community/submissions')).toBe('http://127.0.0.1:8000');
      expect(destination(proxy, '/api/private/community/submissions?limit=50')).toBe('http://127.0.0.1:8000');
    }
  });
});
