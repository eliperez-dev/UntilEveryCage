import { expect, test, type Page } from '@playwright/test';

// Synthetic public projection only. Never retain or print source records.
const releaseId = 'synthetic-resume-release';
const facilityId = '550e8400-e29b-41d4-a716-446655440000';
const wireRecord = {
  facility_id: facilityId, canonical_name: 'Synthetic cache facility', country_code: 'BE', city: 'Synthetic city',
  category: 'slaughter', taxonomy_display_category: 'slaughter', taxonomy_primary_categories: ['slaughter'],
  taxonomy_leaf_activities: [{ key: 'synthetic-activity', label: 'Synthetic activity' }],
  publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed',
  project_approval: 'approved', reviewer_role: null, publication_warning: null,
  display_precision: 'source_reported', latitude: 45, longitude: 5,
  first_observed_at: null, last_observed_at: null, observation_count: 1, lifecycle_status: 'status_unknown',
  source_type: 'official', source_rights_status: 'cleared', provenance_source: null,
  release_id: releaseId, release_ruleset_version: 'synthetic-rules', provenance_source_id: 'synthetic-source',
  provenance_source_name: 'Synthetic source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z',
};
async function mockMap(page: Page) {
  const state = { generation: 1, unavailable: false, feedRequests: 0, manifestRequests: 0 };
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  await page.route('https://server.arcgisonline.com/**', route => route.abort());
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith('/api/')) return route.fallback();
    const identity = { profile: 'official', release_id: releaseId, manifest_sha256: 'a'.repeat(64), suppression_generation: state.generation };
    if (path === '/api/v2/releases/manifest') {
      state.manifestRequests++;
      if (state.unavailable) return route.fulfill({ status: 503, body: '{}' });
      return route.fulfill({ json: { api_version: 'v2', data: { ...identity, manifest: {} } } });
    }
    if (path === '/api/v2/map/feed') {
      state.feedRequests++;
      return route.fulfill({ json: { api_version: 'v2', data: { type: 'FeatureCollection', features: [{ type: 'Feature', id: facilityId, geometry: { type: 'Point', coordinates: [5, 45] }, properties: { facility_id: facilityId, source_id: 'synthetic-source', country_code: 'BE', category_key: 'slaughter', category_keys: ['slaughter'], precision: 'source_reported', weight: 1 } }] }, meta: { ...identity, feature_count: 1, public_record_count: 1, unmapped_count: 0, release_label: 'Synthetic release', dataset_version: 'synthetic' } } });
    }
    if (path === '/api/v2/map/matches') return route.fulfill({ json: { api_version: 'v2', data: { facility_ids: [facilityId] }, meta: { ...identity, total_count: 1, mapped_count: 1 } } });
    if (path === '/api/v2/locations') return route.fulfill({ json: { api_version: 'v2', data: [wireRecord], meta: { release_id: releaseId, ruleset_version: 'synthetic-rules', release_created_at: '2026-01-01T00:00:00Z', profile: 'official', coverage_note: 'Synthetic only.', next_cursor: null, total_count: 1 } } });
    return route.fulfill({ status: 404, body: '{}' });
  });
  return state;
}

async function indexUpdates(page: Page) {
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  const toggle = page.getByRole('button', { name: 'Debug menu', exact: true });
  if (await toggle.getAttribute('aria-expanded') !== 'true') await toggle.click();
  const renderer = page.locator('.map-diagnostics details').filter({ has: page.getByText('Renderer & timing', { exact: true }) });
  if ((await renderer.getAttribute('open')) === null) await renderer.locator('summary').click();
  return Number(await renderer.locator('dl > div').filter({ has: page.locator('dt').filter({ hasText: /^Index updates$/ }) }).locator('dd').textContent());
}

test('retains the filtered public map and built source on a validated warm return without leaking device camera', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { getCurrentPosition: (done: PositionCallback) => done({ coords: { latitude: 12.3456789, longitude: 67.8912345 } } as GeolocationPosition) } });
  });
  const fixture = await mockMap(page);
  await page.goto(`./#/map?release_id=${releaseId}&q=Synthetic&country=BE&category=slaughter&precision=source_reported&source_filter=synthetic-source&source=synthetic-source&activity=synthetic-activity`);
  await expect(page.getByRole('button', { name: 'Search map', exact: false })).toBeVisible();
  await expect.poll(() => fixture.feedRequests).toBe(1);
  const canvas = await page.locator('canvas.maplibregl-canvas').elementHandle();
  expect(canvas).not.toBeNull();
  await indexUpdates(page);
  await expect(page.locator('.map-diagnostics dl > div').filter({ has: page.locator('dt').filter({ hasText: /^Filtered \/ loaded mapped$/ }) }).locator('dd')).toHaveText('1 / 1');
  await page.getByRole('button', { name: 'Close debug menu', exact: true }).click();
  await page.getByRole('button', { name: 'Your location', exact: true }).click();
  await expect(page).not.toHaveURL(/12\.345|67\.891/);
  await expect(page.locator('.area-total strong')).toHaveText('1');
  // Changing spatial membership may update the source; warm navigation must not.
  const before = await indexUpdates(page);
  await page.getByRole('button', { name: 'Close debug menu', exact: true }).click();
  const checked = fixture.manifestRequests;
  await page.getByRole('link', { name: 'About', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty', exact: true }).first()).toBeVisible();
  expect(await canvas!.evaluate(element => element.isConnected)).toBe(true);
  await expect(page).toHaveTitle('About · Until Every Cage');
  await expect(page.getByRole('link', { name: 'Map', exact: true })).not.toHaveAttribute('href', /12\.345|67\.891/);
  const returnParams = new URLSearchParams((await page.getByRole('link', { name: 'Map', exact: true }).getAttribute('href'))!.split('?')[1]);
  expect(returnParams.has('q')).toBe(false);
  for (const [key, value] of [['country', 'BE'], ['category', 'slaughter'], ['precision', 'source_reported'], ['source_filter', 'synthetic-source'], ['source', 'synthetic-source'], ['activity', 'synthetic-activity']]) expect(returnParams.get(key!)).toBe(value);
  await page.getByRole('link', { name: 'Map', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Search map', exact: false })).toBeVisible();
  expect(await canvas!.evaluate(element => element.isConnected)).toBe(true);
  expect(await indexUpdates(page)).toBe(before);
  expect(fixture.feedRequests).toBe(1);
  expect(fixture.manifestRequests).toBeGreaterThan(checked);
});

test('replaces the retained projection when current restrictions change while away', async ({ page }) => {
  const fixture = await mockMap(page);
  await page.goto(`./#/map?release_id=${releaseId}`);
  await expect.poll(() => fixture.feedRequests).toBe(1);
  await page.getByRole('link', { name: 'About', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty', exact: true }).first()).toBeVisible();
  fixture.generation = 2;
  await page.getByRole('link', { name: 'Map', exact: true }).click();
  await expect.poll(() => fixture.feedRequests).toBe(2);
  await expect(page.getByRole('button', { name: 'Search map', exact: false })).toBeVisible();
});

test('does not show the retained map if fresh release validation fails', async ({ page }) => {
  const fixture = await mockMap(page);
  await page.goto(`./#/map?release_id=${releaseId}`);
  await expect.poll(() => fixture.feedRequests).toBe(1);
  await page.getByRole('link', { name: 'About', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty', exact: true }).first()).toBeVisible();
  fixture.unavailable = true;
  await page.getByRole('link', { name: 'Map', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('The public release could not be checked.');
  await expect(page.locator('canvas.maplibregl-canvas')).toHaveCount(0);
  await page.getByRole('link', { name: 'About', exact: true }).click();
  await expect(page).toHaveTitle('About · Until Every Cage');
  await page.getByRole('link', { name: 'Map', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('The public release could not be checked.');
  fixture.unavailable = false;
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Search map', exact: false })).toBeVisible();
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible();
  // A fresh validated identity may reuse its persisted public projection;
  // the rejected live map/source was removed above.
  expect(fixture.feedRequests).toBe(1);
});

test('cancels a pending device-location callback when leaving the map', async ({ page }) => {
  await page.addInitScript(() => {
    const mock = {
      completed: 0,
      pending: null as PositionCallback | null,
      getCurrentPosition(done: PositionCallback) { mock.pending = done; },
      complete() {
        const callback = mock.pending;
        mock.pending = null;
        callback?.({ coords: { latitude: 12.3456789, longitude: 67.8912345 } } as GeolocationPosition);
        mock.completed++;
      },
    };
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: mock });
  });
  await mockMap(page);
  await page.goto(`./#/map?release_id=${releaseId}`);
  await page.getByRole('button', { name: 'Your location', exact: true }).click();
  expect(await page.evaluate(() => Boolean((navigator.geolocation as Geolocation & { pending: unknown }).pending))).toBe(true);
  await page.getByRole('link', { name: 'About', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty', exact: true }).first()).toBeVisible();
  // Resolve only after the map action component has unmounted. A timer could
  // resolve before navigation under parallel CPU load and test a different flow.
  await expect(page.locator('.map-navigation')).toHaveCount(0);
  await page.evaluate(() => (navigator.geolocation as Geolocation & { complete(): void }).complete());
  expect(await page.evaluate(() => (navigator.geolocation as Geolocation & { completed: number }).completed)).toBe(1);
  await expect(page).not.toHaveURL(/12\.345|67\.891/);
  await page.getByRole('link', { name: 'Map', exact: true }).click();
  await indexUpdates(page);
  const camera = page.locator('.map-diagnostics dl > div').filter({ has: page.locator('dt').filter({ hasText: /^Zoom \/ bearing \/ pitch$/ }) }).locator('dd');
  await expect(camera).toHaveText('2.00 / 0.0° / 0.0°');
  await expect(page).not.toHaveURL(/12\.345|67\.891/);
});
