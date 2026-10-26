import { expect, test } from '@playwright/test';
import { installEmptyPublicMap } from '../fixtures/empty-public-map';

test('GPU failure leaves public search, records and navigation usable', async ({ page }) => {
  const release = 'synthetic-no-gpu-release';
  const id = '550e8400-e29b-41d4-a716-446655440000';
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.name));
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type: string, ...options: unknown[]) {
      return /^(webgl2?|experimental-webgl)$/.test(type) ? null : Reflect.apply(original, this, [type, ...options]);
    } as typeof original;
  });
  await installEmptyPublicMap(page, release);
  const row = {
    facility_id: id, canonical_name: 'Synthetic GPU-independent record', country_code: 'BE', city: 'Synthetic city',
    category: 'slaughter', publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed',
    project_approval: 'approved', reviewer_role: null, publication_warning: null, display_precision: 'unmapped',
    latitude: null, longitude: null, first_observed_at: null, last_observed_at: null, observation_count: 1,
    lifecycle_status: 'status_unknown', source_type: 'official', source_rights_status: 'cleared', provenance_source: null,
    release_id: release, release_ruleset_version: 'synthetic-rules', provenance_source_id: 'synthetic-source',
    provenance_source_name: 'Synthetic source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z',
  };
  const meta = { profile: 'official', release_id: release, ruleset_version: 'synthetic-rules', next_cursor: null, total_count: 1, coverage_note: 'Synthetic only.' };
  await page.route(url => url.pathname === '/api/v2/locations', route => route.fulfill({ json: { api_version: 'v2', data: [row], meta } }));
  await page.route(url => url.pathname === `/api/v2/locations/${id}`, route => route.fulfill({ json: { api_version: 'v2', data: row,
    meta: { profile: 'official', release_id: release, ruleset_version: 'synthetic-rules', release_created_at: '2026-01-01T00:00:00Z' } } }));
  await page.goto(`./#/map?release_id=${release}&list=open`);
  await expect(page.getByRole('alert')).toHaveText('Map unavailable in this browser.');
  await expect(page.locator('.resume-status')).toHaveCount(0);
  await expect(page.locator('.map-host canvas')).toHaveCount(0);
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link')).toHaveText(['Map', 'Data', 'Contribute', 'About']);
  const search = page.getByRole('combobox', { name: 'Search across public release records' });
  await expect(search).toBeVisible();
  const response = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v2/locations' && new URL(response.url()).searchParams.get('q') === 'synthetic');
  await search.fill('synthetic');
  expect((await response).ok()).toBe(true);
  await page.locator('.record-list button[data-record-id]').first().click();
  await expect(page.locator('.dossier')).toContainText('Synthetic GPU-independent record');
  await page.getByRole('link', { name: 'Open facility page', exact: true }).click();
  await expect(page.locator('.public-record h1')).toHaveText(row.canonical_name);
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'About', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty' })).toBeVisible();
  // Switching to the explicit synthetic fixture unmounts the retained public
  // map, exercising the failed constructor's cleanup within the same page.
  await page.evaluate(() => { location.hash = '#/map?f1a=field&scenario=dense'; });
  await expect(page.getByRole('alert')).toHaveText('Map unavailable in this browser.');
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'About', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty' })).toBeVisible();
  expect(errors).toEqual([]);
});
