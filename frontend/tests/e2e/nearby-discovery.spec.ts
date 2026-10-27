import { expect, test, type Page } from '@playwright/test';
import { expectNearbyScope } from './nearbyMapAssertions';

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
    const detail = rows.find(row => url.pathname === `/api/v2/locations/${row.facility_id}`);
    if (detail) return route.fulfill({ json: { api_version: 'v2', data: detail, meta } });
    if (url.pathname === '/api/v2/map/matches') return route.fulfill({ json: { api_version: 'v2', data: { facility_ids: rows.map(row => row.facility_id) }, meta: { ...identity, total_count: 3, mapped_count: 3 } } });
    if (url.pathname === '/api/v2/map/feed') return route.fulfill({ json: { api_version: 'v2', data: { type: 'FeatureCollection', features: rows.map(row => ({ type: 'Feature', id: row.facility_id, geometry: { type: 'Point', coordinates: [row.longitude, row.latitude] }, properties: { facility_id: row.facility_id, source_id: row.provenance_source_id, category_key: row.category, category_keys: [row.category], country_code: 'FR', precision: 'source_reported', weight: 1 } })) }, meta: { ...identity, feature_count: 3, public_record_count: 3, unmapped_count: 0, release_label: 'Synthetic release', dataset_version: 'synthetic' } } });
    return route.fulfill({ status: 404, json: {} });
  });
  return requests;
}

test('landing nearby entry transfers exactly once into a50mile search without private browser state', async ({ page }) => {
  const calls = await install(page);
  await page.goto('./');
  expect(await page.evaluate(() => (window as any).__nearbyPermissionRequests)).toBe(0);
  await page.getByRole('button', { name: 'Find locations near me', exact: true }).click();
  await expect(page.locator('.area-summary')).toContainText('Near you');
  await expect(page.locator('.area-total strong')).toHaveText('3');
  expect(await page.evaluate(() => (window as any).__nearbyPermissionRequests)).toBe(1);
  await expect.poll(() => calls.filter(url => url.pathname === '/api/v2/map/matches').at(-1)?.searchParams.get('radius_km')).toBe('80.4672');
  for (const value of Object.values(center)) expect(page.url()).not.toContain(String(value));
  expect(await page.evaluate(() => JSON.stringify({ history: history.state, local: { ...localStorage }, session: { ...sessionStorage } }))).not.toContain(String(center.latitude));
  await expectNearbyScope(page, center);
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

test('toolbar nearby search preserves a typed query and radius fit clears the bottom sheet', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const calls = await install(page);
  await page.goto(`./#/map?release_id=${release}`);
  const handle = page.locator('.mobile-sheet-handle'); await handle.click();
  await page.locator('#field-search').fill('synthetic');
  await page.getByRole('button', { name: 'Your location', exact: true }).click();
  await expect(page.locator('.area-total strong')).toHaveText('3');
  await expect.poll(() => calls.filter(url => url.pathname === '/api/v2/map/matches').at(-1)?.searchParams.get('q')).toBe('synthetic');
  await expectNearbyScope(page, center);
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__?.isMoving());
  const target = await page.evaluate(value => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, box = map.getCanvas().getBoundingClientRect();
    return { y: map.project([value.longitude, value.latitude]).y + box.y, top: document.querySelector('.results')!.getBoundingClientRect().top };
  }, center);
  expect(target.y).toBeLessThan(target.top - 10);
  expect(page.url()).not.toContain(String(center.latitude));
});

test('Explore full map interrupts a private flight and restores the public camera before releasing persistence', async ({ page }) => {
  await install(page);
  await page.goto(`./#/map?release_id=${release}&lat=22&lon=11&z=6`);
  await page.getByRole('button', { name: 'Your location', exact: true }).click();
  await expect(page.locator('.area-total strong')).toHaveText('3');
  await expectNearbyScope(page, center);
  await page.evaluate(async point => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const cache = await import('/src/map/tileCache.ts');
    (window as any).__exitObservedUrls = [];
    const replace = history.replaceState.bind(history);
    history.replaceState = (...args) => { (window as any).__exitObservedUrls.push(String(args[2])); return replace(...args); };
    const jump = map.jumpTo.bind(map);
    map.jumpTo = (camera: unknown) => { (window as any).__exitPersistenceAtJump = cache.getTileCacheDiagnostics().persistenceAllowed; return jump(camera); };
    map.flyTo({ center: [point.longitude + .4, point.latitude + .4], zoom: 10, duration: 2000 });
  }, center);
  await page.getByRole('button', { name: 'Explore full map', exact: true }).click();
  await expect(page.locator('.results')).toBeHidden();
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return [Number(map.getCenter().lat.toFixed(4)), Number(map.getCenter().lng.toFixed(4)), map.getZoom()];
  })).toEqual([22, 11, 6]);
  expect(await page.evaluate(() => (window as any).__exitPersistenceAtJump)).toBe(false);
  expect(await page.evaluate(() => (window as any).__exitObservedUrls.every((href: string) => {
    const params = new URLSearchParams(href.split('?')[1] ?? '');
    return params.get('lat') === '22' && params.get('lon') === '11';
  }))).toBe(true);
  await expect(page.locator('.area-summary')).toHaveCount(0);
});

test('individual PNG and optimized pins receive a static hover halo without source or index updates', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await install(page);
  await page.goto(`./#/map?release_id=${release}&lat=${center.latitude}&lon=${center.longitude}&z=12`);
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getLayer('v1-source-pins') && map.isSourceLoaded('locations') && !map.isMoving();
  });
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, source = map.getSource('locations');
    (window as any).__haloSourceChanges = 0;
    for (const key of ['setData', 'setClusterOptions']) {
      const original = source[key].bind(source);
      source[key] = (...args: unknown[]) => { (window as any).__haloSourceChanges++; return original(...args); };
    }
  });
  for (const optimized of [false, true]) {
    if (optimized) {
      await page.getByRole('button', { name: 'More tools', exact: true }).click();
      await page.getByRole('checkbox', { name: 'Use optimized pins', exact: true }).check();
      await page.getByRole('button', { name: 'More tools', exact: true }).click();
    }
    await page.waitForFunction(optimized => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return map.queryRenderedFeatures({ layers: [optimized ? 'source-coordinate-points' : 'v1-source-pins'] }).length > 0;
    }, optimized);
    const pixel = await page.evaluate(({ point, optimized }) => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, value = map.project([point.longitude, point.latitude]);
      const box = map.getCanvas().getBoundingClientRect();
      return { x: value.x + box.x, y: value.y + box.y - (optimized ? 0 : 14) };
    }, { point: center, optimized });
    await page.mouse.move(pixel.x, pixel.y);
    const halo = page.locator('.pin-hover-halo');
    await expect(halo).toBeVisible();
    const style = await halo.evaluate(element => { const css = getComputedStyle(element); return { animation: css.animationName, pointer: css.pointerEvents, radius: css.borderRadius, size: element.getBoundingClientRect().width }; });
    expect(style).toMatchObject({ animation: 'none', pointer: 'none', radius: '50%' });
    expect(style.size).toBeGreaterThanOrEqual(30);
    await page.mouse.move(1400, 850); await expect(halo).toHaveCount(0);
  }
  expect(await page.evaluate(() => (window as any).__haloSourceChanges)).toBe(0);
});
