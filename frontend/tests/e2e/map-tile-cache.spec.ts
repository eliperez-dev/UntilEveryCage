import { expect, test } from '@playwright/test';
import releaseManifest from '../fixtures/release-map/manifest.json' with { type: 'json' };

test('viewed basemap tiles survive zoom return and browser reload, expire correctly, and keep a local world fallback', async ({ page }) => {
  test.setTimeout(60_000);
  const tileRequests = new Map<string, number>();
  const tile = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/F2sAAAAASUVORK5CYII=', 'base64');
  const solidTile = async (color: string) => Buffer.from(await page.evaluate(color => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 256;
    const context = canvas.getContext('2d')!; context.fillStyle = color; context.fillRect(0, 0, 256, 256);
    return canvas.toDataURL('image/png').split(',')[1]!;
  }, color), 'base64');
  const streetTile = await solidTile('#2060a0'), satelliteTile = await solidTile('#503020');
  await page.route('https://tile.openstreetmap.org/**', route => {
    const url = route.request().url(); tileRequests.set(url, (tileRequests.get(url) ?? 0) + 1);
    return route.fulfill({ status: 200, contentType: 'image/png', body: streetTile, headers: {
      'cache-control': 'public,max-age=86400', expires: new Date(Date.now() + 86400_000).toUTCString(), 'access-control-allow-origin': '*',
    } });
  });
  await page.route('https://server.arcgisonline.com/**', route => route.fulfill({ status: 200, contentType: 'image/png',
    body: route.request().url().includes('World_Imagery') ? satelliteTile : tile,
    headers: { 'cache-control': 'max-age=86400', 'access-control-allow-origin': '*' },
  }));
  await page.route(url => url.pathname === '/api/v2/releases/manifest', route => route.fulfill({ json: releaseManifest }));
  await page.route(url => url.pathname === '/api/v2/map/feed', route => route.fulfill({ json: {
    api_version: 'v2', data: { type: 'FeatureCollection', features: [] }, meta: {
      profile: 'official', release_id: 'synthetic-release-2026-09', manifest_sha256: 'a'.repeat(64), suppression_generation: 7,
      feature_count: 0, public_record_count: 0, unmapped_count: 0, release_label: 'Synthetic tile test', dataset_version: 'synthetic-test',
    },
  } }));
  await page.route(url => url.pathname === '/api/v2/locations', route => route.fulfill({ json: { api_version: 'v2', data: [], meta: { profile: 'official', release_id: 'synthetic-release-2026-09', ruleset_version: 'rules-v1', coverage_note: 'Synthetic tile test.', total_count: 0, next_cursor: null } } }));
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=20&lon=0&z=4');
  const waitForBase = () => page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getSource('base') && map.isSourceLoaded('base') && map.isStyleLoaded();
  });
  await waitForBase();
  expect(tileRequests.size).toBeGreaterThan(0);
  const initialRequests = new Map(tileRequests);
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ zoom: 7 }));
  await waitForBase();
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ zoom: 4 }));
  await waitForBase();
  for (const [url, count] of initialRequests) expect(tileRequests.get(url)).toBe(count);
  await page.reload();
  await waitForBase();
  for (const [url, count] of initialRequests) expect(tileRequests.get(url)).toBe(count);
  const stored = await page.evaluate(async () => {
    const cache = await caches.open('uec-viewed-map-tiles-v1');
    const keys = await cache.keys();
    for (const key of keys) {
      const response = await cache.match(key); if (!response) continue;
      const headers = new Headers(response.headers); headers.set('x-uec-expiry', String(Date.now() - 1000));
      await cache.put(key, new Response(await response.arrayBuffer(), { headers }));
    }
    return keys.map(key => key.url);
  });
  expect(stored.length).toBeGreaterThan(0);
  expect(stored.every(key => /\/__uec_tile_cache__\/[a-f0-9]{64}$/.test(key))).toBe(true);
  await page.reload();
  await waitForBase();
  expect([...initialRequests].some(([url, count]) => (tileRequests.get(url) ?? 0) > count)).toBe(true);
  const world = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return { layers: map.getStyle().layers.map((layer: any) => layer.id),
      localWorld: typeof map.getStyle().sources['world-land'].data === 'object',
      worldFeatures: map.queryRenderedFeatures({ layers: ['world-land'] }).length };
  });
  expect(world.localWorld).toBe(true);
  expect(world.layers.indexOf('world-streets-roads')).toBeLessThan(world.layers.indexOf('base'));
  expect(world.layers.indexOf('world-satellite')).toBeLessThan(world.layers.indexOf('base'));
  expect(world.worldFeatures).toBeGreaterThan(0);
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const colors: number[][] = []; (window as any).__tileHandoffFrames = colors;
    const listener = () => {
      const canvas = map.getCanvas(), gl = canvas.getContext('webgl2'), pixel = new Uint8Array(4);
      gl.readPixels(Math.floor(canvas.width / 2), Math.floor(canvas.height / 2), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
      colors.push(Array.from(pixel));
    };
    map.on('render', listener); (window as any).__stopTileHandoffFrames = () => map.off('render', listener);
  });
  await page.locator('.map-navigation').getByRole('button', { name: 'Satellite', exact: true }).click();
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.getStyle().sources.base.tiles[0].includes('World_Imagery') && !map.getLayer('candidate-base') && map.isSourceLoaded('base');
  })).toBe(true);
  const frames = await page.evaluate(() => {
    (window as any).__stopTileHandoffFrames();
    return { colors: (window as any).__tileHandoffFrames as number[][],
      fade: (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('base', 'raster-fade-duration') };
  });
  expect(frames.fade).toBe(180);
  expect(frames.colors.length).toBeGreaterThan(0);
  expect(frames.colors.some(pixel => pixel[0]! > 200 && pixel[1]! > 200 && pixel[2]! > 200)).toBe(false);

  // Exercise the actual debug callbacks against storage and MapLibre, rather
  // than only checking that range controls display their chosen value.
  await page.locator('.map-navigation').getByRole('button', { name: 'Street', exact: true }).click();
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.getStyle().sources.base.tiles[0].includes('openstreetmap') && !map.getLayer('candidate-base') && map.isSourceLoaded('base');
  })).toBe(true);
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByLabel('Enable debug menu', { exact: true }).check();
  await page.getByRole('button', { name: 'Close more tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  const debug = page.getByRole('complementary', { name: 'Debug menu', exact: true });
  await debug.locator('details.cache-controls > summary').click();
  const fade = debug.locator('#debug-tile-fade');
  await expect(fade).toHaveValue('180');
  await fade.press('End');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('base', 'raster-fade-duration'))).toBe(400);
  await fade.press('Home');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('base', 'raster-fade-duration'))).toBe(0);
  const ram = debug.locator('#debug-ram-tiles');
  await ram.press('Home');
  await expect(ram).toHaveValue('32');
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return { limit: map._maxTileCacheSize,
      managers: Object.values(map.style.tileManagers).every((manager: any) => manager._maxTileCacheSize === 32 && manager._outOfViewCache.max <= 32) };
  })).toEqual({ limit: 32, managers: true });
  await ram.press('End');
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map._maxTileCacheSize === 256 && Object.values(map.style.tileManagers).every((manager: any) => manager._maxTileCacheSize === 256);
  })).toBe(true);
  const baseline = debug.locator('#debug-baseline-opacity');
  await baseline.press('Home');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('world-land', 'fill-opacity'))).toBe(0);
  await baseline.press('End');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('world-land', 'fill-opacity'))).toBe(1);
  await debug.locator('#debug-tile-budget').press('Home');
  await debug.locator('#debug-tile-entries').press('Home');
  await debug.locator('#debug-tile-ttl').press('Home');
  await expect(debug.locator('#debug-tile-budget')).toHaveValue('4');
  await expect(debug.locator('#debug-tile-entries')).toHaveValue('32');
  await expect(debug.locator('#debug-tile-ttl')).toHaveValue('1');
  await debug.getByRole('button', { name: 'Clear map tiles', exact: true }).click();
  const storedTiles = () => page.evaluate(async () => {
    const cache = await caches.open('uec-viewed-map-tiles-v1');
    const entries = await Promise.all((await cache.keys()).map(async key => {
      const response = await cache.match(key); if (!response) return null;
      return { expiry: Number(response.headers.get('x-uec-expiry')), stored: Number(response.headers.get('x-uec-stored')), bytes: Number(response.headers.get('x-uec-size')) };
    }));
    return entries.filter((entry): entry is NonNullable<typeof entry> => entry !== null);
  });
  await expect.poll(async () => (await storedTiles()).length).toBe(0);
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ center: [80, 20], zoom: 6 }));
  await waitForBase();
  const freshTiles = await storedTiles();
  expect(freshTiles.length).toBeGreaterThan(0);
  expect(freshTiles.length).toBeLessThanOrEqual(32);
  expect(freshTiles.reduce((total, entry) => total + entry.bytes, 0)).toBeLessThanOrEqual(4 * 1048576);
  expect(freshTiles.every(entry => entry.expiry <= entry.stored + 3600000)).toBe(true);
  await debug.getByLabel('Cache map tiles', { exact: true }).uncheck();
  await expect(debug.locator('#debug-tile-ttl')).toBeDisabled();
  await debug.getByRole('button', { name: 'Clear map tiles', exact: true }).click();
  await expect.poll(async () => (await storedTiles()).length).toBe(0);
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ center: [-80, -20], zoom: 6 }));
  await waitForBase();
  expect((await storedTiles()).length).toBe(0);
  await debug.getByRole('button', { name: 'Reset cache controls', exact: true }).click();
  await expect(fade).toHaveValue('180');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('base', 'raster-fade-duration'))).toBe(180);
  await expect(debug.locator('#debug-tile-budget')).toHaveValue('32');
  await expect(debug.locator('#debug-tile-entries')).toHaveValue('512');
  await expect(debug.locator('#debug-tile-ttl')).toHaveValue('168');
  await expect(debug.getByLabel('Cache map tiles', { exact: true })).toBeChecked();
  await expect(ram).toHaveValue('128');
  await expect(baseline).toHaveValue('1');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__._maxTileCacheSize)).toBe(128);
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ center: [40, 0], zoom: 6 }));
  await waitForBase();
  expect((await storedTiles()).length).toBeGreaterThan(0);
  await debug.getByRole('button', { name: 'Clear map tiles', exact: true }).click();
  await expect.poll(async () => (await storedTiles()).length).toBe(0);
  await page.context().grantPermissions(['geolocation']);
  await page.context().setGeolocation({ latitude: 12.345678, longitude: 98.765432 });
  await page.getByRole('button', { name: 'Your location', exact: true }).click();
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return Math.abs(map.getCenter().lat - 12.345678) < 0.001 && !map.isMoving() && map.isSourceLoaded('base');
  })).toBe(true);
  expect((await storedTiles()).length).toBe(0);
});
