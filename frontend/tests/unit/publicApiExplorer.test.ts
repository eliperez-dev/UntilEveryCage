import { describe, expect, it } from 'vitest';
import { explorerOptions, guardExplorerRequest } from '../../src/app/publicApiExplorer';
const origin = 'https://example.test';
const base = '/v2-preview/';
describe('publicApiExplorer', () => {
  it('allows only documented same-origin public GETs and local spec/schema references', () => {
    for (const path of ['/api/v2/locations', '/api/v2/locations.csv', '/api/v2/releases/manifest', '/api/v2/discovery/filters', '/api/v2/graph/connections', '/v2-preview/reference/public-openapi.json', '/v2-preview/reference/v2-location.schema.json']) {
      const result = guardExplorerRequest({ url: path, headers: { Authorization: 'synthetic-token', Accept: 'application/json' } }, origin, base);
      expect(result.url).toBe(origin + path); expect(result.method).toBe('GET'); expect(result.credentials).toBe('omit'); expect(result.headers).not.toHaveProperty('Authorization');
    }
  });
  it('preserves only case-insensitive content and conditional GET headers', () => {
    const result = guardExplorerRequest({ url: '/api/v2/releases/manifest', headers: { aCcEpT: 'application/json', 'if-NONE-match': '"synthetic-etag"', Cookie: 'synthetic-cookie', authorization: 'synthetic-token', 'X-Other': 'ignored' } }, origin, base);
    expect(result.headers).toEqual({ Accept: 'application/json', 'If-None-Match': '"synthetic-etag"' });
    expect(result.credentials).toBe('omit');
  });
  it('blocks mutations, private paths, external URLs, credentials, and remote specs', () => {
    for (const request of [{url:'/api/v2/locations',method:'POST'},{url:'/api/private/community/submissions'},{url:'https://elsewhere.test/api/v2/locations'},{url:'https://user:pass@example.test/api/v2/locations'},{url:'/external-spec.json'},{url:'/api/v2/releases/../private'}]) expect(() => guardExplorerRequest(request, origin, base)).toThrow(/public GET/);
  });
  it('disables remote validation/configuration, stored authentication and hash routing', () => {
    expect(explorerOptions).toMatchObject({ supportedSubmitMethods: ['get'], validatorUrl: null, queryConfigEnabled: false, persistAuthorization: false, withCredentials: false, deepLinking: false, tryItOutEnabled: false });
  });
});
