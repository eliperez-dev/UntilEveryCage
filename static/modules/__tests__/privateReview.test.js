import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = (file) => readFileSync(resolve(process.cwd(), file), 'utf8');

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

test('readiness asset validates the current registry-driven country set with exact states', () => {
  const matrix = JSON.parse(root('static/private-review/readiness-matrix.json'));
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
