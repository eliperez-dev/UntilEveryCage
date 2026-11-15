import { expect, test, type Page } from '@playwright/test';

const point: [number, number] = [5, 45];
const id = (i: number) => `550e8400-e29b-41d4-a716-${i.toString(16).padStart(12, '0')}`;
const categories = ['slaughter', 'processing_and_preparation', 'research_and_animal_use'];
async function install(page: Page, count: number, labelDelay = 0, spacing = 0) {
  const release = `synthetic-overlap-${count}`;
  page.on('pageerror', error => console.log('Synthetic ring page error:', error.message));
  const state = { feeds: 0, privateRequests: 0, detailRequests: 0, onlyFirst: false };
  const meta = { profile: 'official', release_id: release, ruleset_version: 'synthetic-rules', release_created_at: '2026-01-01T00:00:00Z' };
  const rows = Array.from({ length: count }, (_, i) => ({ facility_id: id(i + 1), canonical_name: `Synthetic facility ${i + 1}`, country_code: 'BE', city: 'Synthetic city', category: categories[i % 3], taxonomy_display_category: categories[i % 3], taxonomy_primary_categories: [categories[i % 3]], publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved', reviewer_role: null, publication_warning: null, display_precision: i % 2 ? 'approximate' : 'source_reported', latitude: point[1], longitude: point[0] + i * spacing, first_observed_at: null, last_observed_at: null, observation_count: 1, lifecycle_status: 'status_unknown', source_type: 'official', source_rights_status: 'cleared', provenance_source: null, release_id: release, release_ruleset_version: 'synthetic-rules', provenance_source_id: 'synthetic-source', provenance_source_name: 'Synthetic source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z' }));
  await page.route('https://**/*', route => route.abort());
  await page.route('**/api/private/**', route => { state.privateRequests++; return route.fulfill({ status: 404, json: {} }); });
  await page.route('**/api/v2/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname;
    const identity = { profile: 'official', release_id: release, manifest_sha256: 'b'.repeat(64), suppression_generation: 1 };
    if (path.includes('/private/') || path.includes('/reference')) { state.privateRequests++; return route.fulfill({ status: 404, json: {} }); }
    if (path === '/api/v2/releases/manifest') return route.fulfill({ json: { api_version: 'v2', data: { ...identity, manifest: {} } } });
    if (path === '/api/v2/map/feed') {
      state.feeds++;
      return route.fulfill({ json: { api_version: 'v2', data: { type: 'FeatureCollection', features: rows.map(row => ({ type: 'Feature', id: row.facility_id, geometry: { type: 'Point', coordinates: [row.longitude, row.latitude] }, properties: { facility_id: row.facility_id, source_id: 'synthetic-source', country_code: 'BE', category_key: row.category, category_keys: [row.category], precision: row.display_precision, weight: 1 } })) }, meta: { ...identity, feature_count: count, public_record_count: count, unmapped_count: 0, release_label: 'Synthetic release', dataset_version: 'synthetic' } } });
    }
    if (path === '/api/v2/locations') return route.fulfill({ json: { api_version: 'v2', data: state.onlyFirst ? rows.slice(0, 1) : rows, meta: { ...meta, coverage_note: 'Synthetic renderer checks.', next_cursor: null, total_count: state.onlyFirst ? 1 : count } } });
    const detail = rows.find(row => path === `/api/v2/locations/${row.facility_id}`);
    if (detail) {
      state.detailRequests++;
      if (labelDelay) await new Promise(resolve => setTimeout(resolve, labelDelay));
      return route.fulfill({ json: { api_version: 'v2', data: detail, meta } });
    }
    if (path === '/api/v2/map/matches') { const ids = (state.onlyFirst ? rows.slice(0, 1) : rows).map(row => row.facility_id); return route.fulfill({ json: { api_version: 'v2', data: { facility_ids: ids }, meta: { ...identity, total_count: ids.length, mapped_count: ids.length } } }); }
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto(`./#/map?release_id=${release}&lat=45&lon=5&z=12`);
  await page.waitForFunction(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return m?.getLayer('v1-source-pins') && m.isSourceLoaded('locations') && !m.isMoving(); }, undefined, { timeout: 15000 }).catch(async error => { console.log('Synthetic map startup:', await page.locator('body').innerText(), await page.evaluate(() => ({ map: !!(window as any).__UEC_LOCAL_PREVIEW_MAP__, href: location.href }))); throw error; });
  await expect.poll(() => page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return m.queryRenderedFeatures({ layers: ['v1-source-pins', 'approx-reference-pins', 'public-pin-stack-count'].filter(id => m.getLayer(id)) }).length; })).toBeGreaterThan(0);
  return state;
}
async function clickPoint(page: Page, verticalOffset = 13) {
  const p = await page.evaluate(({ coordinates, verticalOffset }) => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__, p = m.project(coordinates), r = m.getCanvas().getBoundingClientRect(); return { x: r.x + p.x, y: r.y + p.y - verticalOffset }; }, { coordinates: point, verticalOffset });
  await page.mouse.click(p.x, p.y);
}
async function camera(page: Page) { return page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return [m.getCenter().toArray(), m.getZoom(), m.getPitch(), m.getBearing()]; }); }

const overlap = (page: Page) => page.locator('.public-overlap-panel');
const members = (page: Page) => page.locator('.overlap-member');
const marker = (page: Page) => page.locator('.overlap-keyboard-marker');

async function waitForMarker(page: Page, count: number) {
  await expect.poll(() => page.evaluate(expected => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.hasImage('cluster-shared-point')
      && map.getLayer('public-pin-stack-count')
      && map.queryRenderedFeatures({ layers: ['public-pin-stack-count'] }).some((feature: any) => feature.properties.count === expected);
  }, count)).toBe(true);
  await expect(marker(page)).toHaveCount(1);
  const originalPins = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.queryRenderedFeatures({ layers: ['v1-source-pins', 'v1-source-shadows', 'approx-reference-pins', 'approx-reference-shadows', 'source-coordinate-points'] }).length;
  });
  expect(originalPins).toBe(0);
}

for (const mobile of [false, true]) test(`overlap marker opens its records with a fixed camera on ${mobile ? 'phone' : 'desktop'}`, async ({ page }, info) => {
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 });
  const state = await install(page, 8);
  await waitForMarker(page, 8);
  const before = await camera(page);
  await clickPoint(page);
  await expect(overlap(page)).toBeVisible();
  await expect(overlap(page).getByRole('heading')).toContainText('8');
  await expect(members(page)).toHaveCount(8);
  await expect(members(page).nth(1)).toContainText('Synthetic facility 2');
  await expect(members(page).first()).toBeFocused();
  const frame = (await overlap(page).boundingBox())!;
  const canvas = (await page.locator('.maplibregl-canvas').boundingBox())!;
  if (mobile) {
    expect(frame.width).toBeCloseTo(canvas.width, 0);
    expect(frame.y + frame.height).toBeCloseTo(canvas.y + canvas.height, 0);
  } else {
    const pin = (await marker(page).boundingBox())!;
    expect(frame.x).toBeGreaterThan(pin.x + pin.width / 2);
    expect(frame.width).toBeLessThanOrEqual(304);
  }
  expect(await camera(page)).toEqual(before);
  await page.screenshot({ path: info.outputPath(mobile ? 'overlap-phone.png' : 'overlap-desktop.png') });
  await members(page).nth(1).click();
  await expect(overlap(page)).toHaveCount(0);
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${id(2)}`);
  await expect(page.locator('.map-summary')).toContainText('Synthetic facility 2');
  expect(await camera(page)).toEqual(before);
  expect(state.feeds).toBe(1);
  expect(state.privateRequests).toBe(0);
});

for (const count of [214, 614]) test(`${count} records stay keyboard reachable without rebuilding the map source`, async ({ page }) => {
  await page.setViewportSize(count === 614 ? { width: 320, height: 568 } : { width: 1440, height: 900 });
  const state = await install(page, count);
  await waitForMarker(page, count);
  const before = await camera(page);
  await marker(page).press('Enter');
  await expect(overlap(page)).toBeVisible();
  await page.evaluate(() => {
    const source = (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('locations');
    const original = source.setData.bind(source);
    (window as any).__overlapSourceWrites = 0;
    source.setData = (...args: any[]) => { (window as any).__overlapSourceWrites++; return original(...args); };
  });
  await expect(members(page)).toHaveCount(count);
  await members(page).first().press('End');
  const last = members(page).last();
  await expect(last).toBeFocused();
  await expect(last).toBeInViewport();
  await last.press('ArrowUp');
  await expect(members(page).nth(count - 2)).toBeFocused();
  await page.keyboard.press('Home');
  await expect(members(page).first()).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(overlap(page)).toHaveCount(0);
  await expect(marker(page)).toBeFocused();
  expect(await camera(page)).toEqual(before);
  expect(await page.evaluate(() => (window as any).__overlapSourceWrites)).toBe(0);
  expect(state.feeds).toBe(1);
  expect(state.privateRequests).toBe(0);
  expect(state.detailRequests).toBeLessThan(30);
});

test('nearby pins at distinct coordinates stay separate', async ({ page }) => {
  await install(page, 2, 0, 0.00001);
  await expect(marker(page)).toHaveCount(0);
  await clickPoint(page);
  await expect(overlap(page)).toHaveCount(0);
  await expect(page.locator('.map-summary')).toBeVisible();
});

test('single records stay direct', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await install(page, 1);
  await clickPoint(page);
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${id(1)}`);
  await expect(overlap(page)).toHaveCount(0);
});

test('optimized overlap markers and coincident native clusters open the list', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await install(page, 18);
  const more = page.getByRole('button', { name: 'More tools', exact: true });
  await more.click();
  await page.getByText('Advanced', { exact: true }).click();
  await page.getByRole('checkbox', { name: 'Use optimized pins', exact: true }).check();
  await page.locator('#map-clustering-choice').selectOption('off');
  await more.click();
  await waitForMarker(page, 18);
  await clickPoint(page, 5);
  await expect(members(page)).toHaveCount(18);
  await page.keyboard.press('Escape');
  await expect(overlap(page)).toHaveCount(0);
  await more.click();
  await page.getByText('Advanced', { exact: true }).click();
  await page.locator('#map-clustering-choice').selectOption('on');
  await more.click();
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ zoom: 4 }));
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.queryRenderedFeatures({ layers: ['clusters'] }).length)).toBeGreaterThan(0);
  const before = await camera(page);
  await clickPoint(page, 0);
  await expect(members(page)).toHaveCount(18);
  expect(await camera(page)).toEqual(before);
});

test('new query membership clears the old overlap and count', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const state = await install(page, 81);
  await waitForMarker(page, 81);
  await clickPoint(page);
  await expect(overlap(page)).toBeVisible();
  state.onlyFirst = true;
  await page.locator('#field-search').fill('only first');
  await page.locator('#field-search').press('Enter');
  await expect(overlap(page)).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('locations').getData().then((d: any) => d.features.length))).toBe(1);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('public-pin-stacks').getData().then((d: any) => d.features.length))).toBe(0);
  await expect(marker(page)).toHaveCount(0);
  expect(state.privateRequests).toBe(0);
});
