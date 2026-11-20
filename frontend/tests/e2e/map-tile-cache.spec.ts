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
});
