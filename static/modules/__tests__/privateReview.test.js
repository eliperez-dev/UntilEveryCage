import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';

const root = (file) => readFileSync(resolve(process.cwd(), file), 'utf8');

function generateReadinessMatrix() {
  const dir = mkdtempSync(resolve(tmpdir(), 'uec-readiness-'));
  const output = resolve(dir, 'readiness-matrix.json');
  try {
    execFileSync('python', ['pipeline/scripts/diagnostics/build-review-console-snapshot.py', output], { cwd: process.cwd() });
    return JSON.parse(readFileSync(output, 'utf8'));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test('private review console is read-only and uses the existing authenticated read contracts', () => {
  const html = root('static/private-review.html');
  const js = root('static/private-review.js');
  const css = root('static/private-review.css');

  expect(html).toContain('PRIVATE ONLY');
  expect(html).toContain('X-UEC-Dev-Preview-Token');
  expect(html).toContain('X-UEC-Private-Graph-Token');
  expect(js).toContain('/api/dev/preview/candidates');
  expect(js).toContain('/api/private/graph/queues/');
  expect(js).toContain('/api/private/graph/entities');
  expect(js).toContain('/neighborhood');
  expect(js).toContain('no-store');
  expect(js).not.toMatch(/localStorage|sessionStorage/);
  expect(js).not.toMatch(/method\s*:\s*['"](?:POST|PUT|PATCH|DELETE)['"]/i);
  expect(html).not.toMatch(/<button[^>]*>\s*(?:publish|promote|approve|release|export)\b/i);
  expect(css).toContain('.overview-rail');
  expect(css).toContain('.readiness-matrix');
  expect(css).toContain('@media');
});

test('readiness generator produces a valid registry-driven snapshot without requiring committed output', () => {
  const matrix = generateReadinessMatrix();
  const states = ['infrastructure-only', 'acquisition-ready', 'private-candidate-ready', 'human-review-ready', 'publication-eligible', 'blocked'];
  expect(matrix.derived_context).toBe(true);
  expect(matrix.states).toEqual(states);
  expect(Number.isInteger(matrix.country_count)).toBe(true);
  const countries = Object.entries(matrix.countries);
  expect(countries).toHaveLength(matrix.country_count);
  expect(countries.length).toBeGreaterThan(0);
  for (const [countryCode, country] of countries) {
    expect(countryCode).toMatch(/^[A-Z]{2}$/);
    expect(states).toContain(country.state);
    expect(country).toEqual(expect.objectContaining({ name: expect.any(String), summary: expect.any(String), basis: expect.any(Array) }));
  }
  expect(matrix.countries.BE.sources[0].attribution.terms_status).toBe('pending-human-review');
  expect(matrix.countries.BE.sources[0].status.acquisition).toBe('artifact_private_only');
});

test('safe review page never includes private address, raw payload, geocoder, or requester fields', () => {
  const js = root('static/private-review.js');
  const combined = `${root('static/private-review.html')}\n${js}`.toLowerCase();
  for (const forbidden of ['requester details', 'raw source payloads', 'geocoder requests/responses', 'private addresses']) {
    expect(combined).toContain(forbidden);
  }
  expect(js).toContain('Withheld by console');
  expect(js.toLowerCase()).toContain('observations remain separate');
});

test('review packet loader rejects row-shaped payloads and keeps tokens out of storage APIs', async () => {
  const { validateReviewPacket, validateReadinessPayload } = await import('../../private-review.js');
  expect(() => validateReviewPacket({ schema_version: 'private-review-packet-v2', counts: { input_rows: 1 } })).not.toThrow();
  expect(() => validateReviewPacket({ schema_version: 'private-review-packet-v2', normalized: { records: [] } })).toThrow('rejected safely');
  expect(() => validateReviewPacket({ schema_version: 'private-review-packet-v2', counts: { input_rows: 1 }, provenance: { raw_payload_alias: 'withheld' } })).toThrow('rejected safely');
  expect(() => validateReviewPacket({ schema_version: 'private-review-packet-v2', quarantine: { reasons: { raw_payload_alias: 'withheld' } } })).toThrow('rejected safely');
  expect(() => validateReadinessPayload(generateReadinessMatrix())).not.toThrow();
  expect(() => validateReadinessPayload({ schema_version: 'private-review-console-v1', derived_context: true, countries: {} })).toThrow('rejected safely');
});
