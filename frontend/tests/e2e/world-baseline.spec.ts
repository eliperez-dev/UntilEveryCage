import { expect, test } from '@playwright/test';
import releaseManifest from '../fixtures/release-map/manifest.json' with { type: 'json' };

async function installWorldFixture(page: import('@playwright/test').Page, actualProviders = false) {
  const transparent = Buffer.from(await page.evaluate(() => document.createElement('canvas').toDataURL('image/png').split(',')[1]!), 'base64');
  if (!actualProviders) {
    await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ contentType: 'image/png', body: transparent }));
    await page.route('https://server.arcgisonline.com/**', route => route.fulfill({ contentType: 'image/png', body: transparent }));
  }
  await page.route(url => url.pathname === '/api/v2/releases/manifest', route => route.fulfill({ json: releaseManifest }));
  await page.route(url => url.pathname === '/api/v2/map/feed', route => route.fulfill({ json: {
    api_version: 'v2', data: { type: 'FeatureCollection', features: [] }, meta: {
      profile: 'official', release_id: 'synthetic-release-2026-09', manifest_sha256: 'a'.repeat(64), suppression_generation: 7,
      feature_count: 0, public_record_count: 0, unmapped_count: 0, release_label: 'Synthetic world test', dataset_version: 'synthetic-test',
    },
  } }));
  await page.route(url => url.pathname === '/api/v2/locations', route => route.fulfill({ json: { api_version: 'v2', data: [], meta: { profile: 'official', release_id: 'synthetic-release-2026-09', ruleset_version: 'rules-v1', coverage_note: 'Synthetic world test.', total_count: 0, next_cursor: null } } }));
}

test('satellite imagery stays backed by bounded local tiles through detailed 2D and 3D zoom', async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1280, height: 900 });
  // No facility records; provider imagery and the bundled fallback are real.
  await installWorldFixture(page, true);
  await page.addInitScript(() => { Object.defineProperty(navigator, 'connection', { configurable: true, value: { saveData: true } }); });
  const ranges: string[] = [], whole: string[] = [];
  page.on('request', request => {
    if (request.url().includes('/world-baseline/') && request.url().endsWith('.bin'))
      (request.headers().range ? ranges : whole).push(request.url());
  });
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=48&lon=10&z=8');
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.isStyleLoaded());
  await page.getByRole('button', { name: 'Tools', exact: true }).click();
  await page.getByLabel('Map style').selectOption('satellite');
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.getStyle().sources.base.tiles[0].includes('World_Imagery') && !map.getLayer('candidate-base') && map.isSourceLoaded('base');
  }), { timeout: 30_000 }).toBe(true);
  await page.getByRole('button', { name: 'Close Tools', exact: true }).click();
  for (const pitch of [0, 55]) {
    for (const zoom of [9, 7, 10]) {
      await page.evaluate(({ zoom, pitch }) => (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom, pitch, duration: 450 }), { zoom, pitch });
      await page.waitForFunction(() => {
        const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
        return !map.isMoving() && map.isSourceLoaded('base') && map.isSourceLoaded('world-satellite');
      });
    }
    if (pitch) expect(await page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__.getTerrain()))).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`satellite-${pitch ? '3d' : '2d'}.png`) });
    // Remove detail only: the same high-zoom viewport must keep actual coarse
    // imagery, rather than revealing the flat Natural Earth backing.
    await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      map.setPaintProperty('base', 'raster-opacity', 0);
      map.setPaintProperty('transport', 'raster-opacity', 0);
    });
    await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.isSourceLoaded('world-satellite'));
    const fallback = await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, style = map.getStyle();
      const layer = style.layers.find((layer: any) => layer.id === 'world-satellite');
      const manager = map.style.tileManagers['world-satellite'];
      return { maxzoom: style.sources['world-satellite'].maxzoom, layerMaxzoom: layer.maxzoom ?? null,
        visible: layer.layout.visibility, tiles: manager.getRenderableIds().length,
        zooms: manager.getRenderableIds().map((id: string) => manager.getTileByID(id)?.tileID?.canonical?.z).filter((z: unknown) => typeof z === 'number') };
    });
    expect(fallback).toMatchObject({ maxzoom: 5, layerMaxzoom: null, visible: 'visible' });
    expect(fallback.tiles).toBeGreaterThan(0);
    expect(fallback.zooms.every((zoom: number) => zoom <= 5)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`satellite-fallback-${pitch ? '3d' : '2d'}.png`) });
    await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      map.setPaintProperty('base', 'raster-opacity', 1); map.setPaintProperty('transport', 'raster-opacity', .72);
    });
  }
  expect(whole).toHaveLength(0);
  expect(ranges.length).toBeGreaterThan(0);
  expect(ranges.every(url => /-z[0-5]\./.test(url))).toBe(true);
  await page.getByRole('button', { name: 'Tools', exact: true }).click();
  await page.getByLabel('Enable debug menu', { exact: true }).check();
  await page.getByRole('button', { name: 'Close Tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  const debug = page.getByRole('complementary', { name: 'Debug menu', exact: true });
  await debug.locator('details.cache-controls > summary').click();
  await expect(debug.locator('#debug-tile-fade')).toBeDisabled();
  await expect(debug.getByText('Unavailable with terrain', { exact: true })).toBeVisible();
});

test('real local world streets and satellite warm through z5 and survive a full reload', async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1280, height: 900 });
  await installWorldFixture(page);
  const wholeRequests: string[] = [];
  page.on('request', request => { if (request.url().includes('/world-baseline/') && request.url().endsWith('.bin') && !request.headers().range) wholeRequests.push(request.url()); });
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=48&lon=10&z=4');
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getLayer('world-streets-roads') ? map.queryRenderedFeatures({ layers: ['world-streets-roads'] }).length : 0;
  }), { timeout: 30_000 }).toBeGreaterThan(0);
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getLayer('world-streets-labels') ? map.queryRenderedFeatures({ layers: ['world-streets-labels'] }).length : 0;
  }), { timeout: 15_000 }).toBeGreaterThan(0);
  const cacheStats = () => page.evaluate(async () => {
    const cache = await caches.open('uec-world-baseline-v1'), keys = await cache.keys();
    const values = await Promise.all(keys.map(async key => (await cache.match(key))?.arrayBuffer()));
    return { entries: keys.length, bytes: values.reduce((sum, value) => sum + (value?.byteLength ?? 0), 0), local: keys.every(key => new URL(key.url).origin === location.origin) };
  });
  await expect.poll(cacheStats, { timeout: 30_000 }).toEqual({ entries: 12, bytes: 16899100, local: true });
  await page.screenshot({ path: testInfo.outputPath('world-streets.png') });
  await page.getByRole('button', { name: 'Tools', exact: true }).click();
  await page.getByLabel('Map style').selectOption('satellite');
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.getLayoutProperty('world-satellite', 'visibility') === 'visible' && map.getLayoutProperty('world-streets-roads', 'visibility') === 'none';
  })).toBe(true);
  await page.getByRole('button', { name: 'Close Tools', exact: true }).click();
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.isStyleLoaded());
  await page.screenshot({ path: testInfo.outputPath('world-satellite.png') });
  wholeRequests.length = 0;
  await page.reload();
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.isStyleLoaded());
  await expect.poll(cacheStats).toEqual({ entries: 12, bytes: 16899100, local: true });
  expect(wholeRequests).toHaveLength(0);
  await page.getByRole('button', { name: 'Tools', exact: true }).click();
  await page.getByLabel('Enable debug menu', { exact: true }).check();
  await page.getByRole('button', { name: 'Close Tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  const debug = page.getByRole('complementary', { name: 'Debug menu', exact: true });
  await debug.locator('details.cache-controls > summary').click();
  await debug.locator('#debug-world-zoom').press('Home');
  await expect.poll(cacheStats).toEqual({ entries: 2, bytes: 72567, local: true });
  await debug.locator('#debug-world-budget').press('Home');
  await debug.locator('#debug-world-zoom').press('End');
  await expect.poll(cacheStats, { timeout: 15_000 }).toEqual({ entries: 11, bytes: 7877453, local: true });
  await debug.getByLabel('Preload world map', { exact: true }).uncheck();
  await expect(debug.locator('#debug-world-zoom')).toBeDisabled();
  await debug.getByRole('button', { name: 'Clear world map cache', exact: true }).click();
  await expect.poll(cacheStats).toEqual({ entries: 0, bytes: 0, local: true });
  await debug.getByRole('button', { name: 'Reset cache controls', exact: true }).click();
  await expect.poll(cacheStats, { timeout: 15_000 }).toEqual({ entries: 12, bytes: 16899100, local: true });
});

test('fresh mobile world warm-up stops at the exact z4 tier', async ({ page }) => {
  test.setTimeout(45_000);
  await page.setViewportSize({ width: 375, height: 844 });
  await installWorldFixture(page);
  const wholeRequests: string[] = [];
  page.on('request', request => { if (request.url().includes('/world-baseline/') && request.url().endsWith('.bin') && !request.headers().range) wholeRequests.push(request.url()); });
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=48&lon=10&z=7');
  await expect.poll(() => page.evaluate(async () => {
    const cache = await caches.open('uec-world-baseline-v1'), keys = await cache.keys();
    const values = await Promise.all(keys.map(async key => (await cache.match(key))?.arrayBuffer()));
    return { entries: keys.length, bytes: values.reduce((sum, value) => sum + (value?.byteLength ?? 0), 0) };
  }), { timeout: 30_000 }).toEqual({ entries: 10, bytes: 6716971 });
  expect(wholeRequests).toHaveLength(10);
  expect(wholeRequests.some(url => /-z5\./.test(url))).toBe(false);
});

test('Save-Data skips background world downloads after the map becomes idle', async ({ page }) => {
  test.setTimeout(30_000);
  await page.addInitScript(() => { Object.defineProperty(navigator, 'connection', { configurable: true, value: { saveData: true } }); });
  await installWorldFixture(page);
  const wholeRequests: string[] = [];
  page.on('request', request => { if (request.url().includes('/world-baseline/') && request.url().endsWith('.bin') && !request.headers().range) wholeRequests.push(request.url()); });
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=48&lon=10&z=7');
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.isStyleLoaded());
  await page.evaluate(() => new Promise<void>(resolve => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    map.once('idle', () => requestIdleCallback(() => requestIdleCallback(() => resolve(), { timeout: 2000 }), { timeout: 2000 }));
    map.triggerRepaint();
  }));
  expect(wholeRequests).toHaveLength(0);
  expect(await page.evaluate(async () => (await (await caches.open('uec-world-baseline-v1')).keys()).length)).toBe(0);
});
