import { expect, test, type Page } from '@playwright/test';

const release = 'synthetic-nearby-discovery';
const center = { latitude: 45.123456, longitude: 5.678912 };
async function install(page: Page) {
  const requests: URL[] = [];
  const rows = ['slaughter', 'processing_and_preparation', 'animal_keeping_and_production'].map((category, i) => ({
    facility_id: `550e8400-e29b-41d4-a716-44665544000${i}`, canonical_name: `Synthetic nearby ${i}`,
    country_code: 'FR', city: 'Synthetic locality', category, taxonomy_display_category: category, taxonomy_primary_categories: [category],
    publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved',
    reviewer_role: null, publication_warning: null, display_precision: 'source_reported', latitude: center.latitude + i * .05,
    longitude: center.longitude + i * .08, first_observed_at: null, last_observed_at: null, observation_count: 1,
    lifecycle_status: 'status_unknown', source_type: 'official', source_rights_status: 'cleared', provenance_source: null,
    release_id: release, release_ruleset_version: 'synthetic', provenance_source_id: 'synthetic-register', provenance_source_name: 'Synthetic register',
    provenance_source_url: 'https://example.test/register', provenance_retrieved_at: '2026-01-01T00:00:00Z',
  }));
  const identity = { release_id: release, profile: 'official', manifest_sha256: 'a'.repeat(64), suppression_generation: 0 };
  const meta = { release_id: release, profile: 'official', ruleset_version: 'synthetic', release_created_at: '2026-01-01T00:00:00Z' };
  await page.addInitScript(value => {
    (window as any).__nearbyPermissionRequests = 0;
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition(success: (p: unknown) => void) {
      (window as any).__nearbyPermissionRequests++;
      queueMicrotask(() => success({ coords: value }));
    } } });
  }, center);
  await page.route('https://**/*', route => route.abort());
  await page.route('**/api/v2/**', route => {
    const url = new URL(route.request().url()); requests.push(url);
    if (url.pathname === '/api/v2/releases/manifest') return route.fulfill({ json: { api_version: 'v2', data: { ...identity, manifest: {} } } });
    if (url.pathname === '/api/v2/locations') return route.fulfill({ json: { api_version: 'v2', data: rows, meta: { ...meta, coverage_note: 'Synthetic test scope.', total_count: 3, next_cursor: null } } });
    if (url.pathname === '/api/v2/map/matches') return route.fulfill({ json: { api_version: 'v2', data: { facility_ids: rows.map(row => row.facility_id) }, meta: { ...identity, total_count: 3, mapped_count: 3 } } });
    if (url.pathname === '/api/v2/map/feed') return route.fulfill({ json: { api_version: 'v2', data: { type: 'FeatureCollection', features: rows.map(row => ({ type: 'Feature', id: row.facility_id, geometry: { type: 'Point', coordinates: [row.longitude, row.latitude] }, properties: { facility_id: row.facility_id, source_id: row.provenance_source_id, category_key: row.category, category_keys: [row.category], country_code: 'FR', precision: 'source_reported', weight: 1 } })) }, meta: { ...identity, feature_count: 3, public_record_count: 3, unmapped_count: 0, release_label: 'Synthetic release', dataset_version: 'synthetic' } } });
    return route.fulfill({ status: 404, json: {} });
  });
  return requests;
}

test('landing nearby entry transfers exactly once into a100mile search without private browser state', async ({ page }) => {
  const calls = await install(page);
  await page.goto('./');
  expect(await page.evaluate(() => (window as any).__nearbyPermissionRequests)).toBe(0);
  await page.getByRole('button', { name: 'Find locations near me', exact: true }).click();
  await expect(page.locator('.area-summary')).toContainText('Near you');
  await expect(page.locator('.area-total strong')).toHaveText('3');
  expect(await page.evaluate(() => (window as any).__nearbyPermissionRequests)).toBe(1);
  await expect.poll(() => calls.filter(url => url.pathname === '/api/v2/map/matches').at(-1)?.searchParams.get('radius_km')).toBe('160.9344');
  for (const value of Object.values(center)) expect(page.url()).not.toContain(String(value));
  expect(await page.evaluate(() => JSON.stringify({ history: history.state, local: { ...localStorage }, session: { ...sessionStorage } }))).not.toContain(String(center.latitude));
  await page.getByRole('button', { name: 'Fit results', exact: true }).click();
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__?.isMoving());
  const geometry = await page.evaluate(value => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, host = map.getCanvas().getBoundingClientRect();
    const rail = document.querySelector('.results')!.getBoundingClientRect(), point = map.project([value.longitude, value.latitude]);
    return { x: point.x + host.x, y: point.y + host.y, railRight: rail.right, railTop: rail.top, width: host.width };
  }, center);
  expect(geometry.x).toBeGreaterThan(geometry.railRight + 10);
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.panBy([50, 0], { duration: 0 }));
  for (const value of Object.values(center)) expect(page.url()).not.toContain(String(value));
  await page.reload();
  expect(await page.evaluate(() => (window as any).__nearbyPermissionRequests)).toBe(0);
  await expect(page.locator('.area-summary')).toHaveCount(0);
});

test('toolbar nearby search preserves a typed query and mobile fit clears the bottom sheet', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const calls = await install(page);
  await page.goto(`./#/map?release_id=${release}`);
  const handle = page.locator('.mobile-sheet-handle'); await handle.click();
  await page.locator('#field-search').fill('synthetic');
  await page.getByRole('button', { name: 'Your location', exact: true }).click();
  await expect(page.locator('.area-total strong')).toHaveText('3');
  await expect.poll(() => calls.filter(url => url.pathname === '/api/v2/map/matches').at(-1)?.searchParams.get('q')).toBe('synthetic');
  await page.getByRole('button', { name: 'Fit results', exact: true }).click();
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__?.isMoving());
  const target = await page.evaluate(value => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, box = map.getCanvas().getBoundingClientRect();
    return { y: map.project([value.longitude, value.latitude]).y + box.y, top: document.querySelector('.results')!.getBoundingClientRect().top };
  }, center);
  expect(target.y).toBeLessThan(target.top - 10);
  expect(page.url()).not.toContain(String(center.latitude));
});
