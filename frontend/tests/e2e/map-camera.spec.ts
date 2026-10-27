import { expect, test } from '@playwright/test';
import releaseManifest from '../fixtures/release-map/manifest.json' with { type: 'json' };
import { labRecords } from '../../src/design-lab/fixtures';

const cameraFixtureId = '223e4567-e89b-42d3-a456-426614174000';
const cameraFixturePoint: [number, number] = [4.45, 50.95];
// A style change prepares a candidate, then the base, each with a 10s bound.
const basemapHandoffTimeout = 22_000;
async function installPublicCameraFixture(page: import('@playwright/test').Page) {
  const releaseId = 'synthetic-release-2026-09';
  const requests = { manifests: 0, feeds: 0 };
  await page.route(url => url.pathname === '/api/v2/releases/manifest', route => { requests.manifests++; return route.fulfill({ status: 200, json: releaseManifest }); });
  await page.route(url => url.pathname === '/api/v2/map/feed', route => { requests.feeds++; return route.fulfill({ status: 200, json: {
    api_version: 'v2', data: { type: 'FeatureCollection', features: [{ type: 'Feature', id: cameraFixtureId,
      geometry: { type: 'Point', coordinates: cameraFixturePoint }, properties: { facility_id: cameraFixtureId,
        source_id: 'fixture.source', category_key: 'slaughter', category_keys: ['slaughter'], precision: 'approximate', weight: 1 } }] },
    meta: { profile: 'official', release_id: releaseId, manifest_sha256: 'a'.repeat(64), suppression_generation: 7,
      feature_count: 1, public_record_count: 1, unmapped_count: 0, release_label: 'Synthetic camera fixture', dataset_version: 'synthetic-test' },
  } }); });
  await page.route(url => url.pathname === '/api/v2/locations', route => route.fulfill({ status: 200, json: {
    api_version: 'v2', data: [{ facility_id: cameraFixtureId, canonical_name: 'Synthetic camera fixture', country_code: 'BE', city: 'Synthetic place',
      category: 'slaughter', publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed',
      project_approval: 'approved', reviewer_role: null, publication_warning: null, display_precision: 'approximate',
      latitude: cameraFixturePoint[1], longitude: cameraFixturePoint[0], first_observed_at: null, last_observed_at: null, observation_count: 1,
      lifecycle_status: 'active_observed', source_type: 'official', source_rights_status: 'cleared', provenance_source: null,
      provenance_source_id: 'fixture.source', provenance_source_name: 'Synthetic source', provenance_source_url: 'https://example.test/source',
      provenance_retrieved_at: '2026-01-01T00:00:00Z', release_id: releaseId, release_ruleset_version: 'rules-v1' }],
    meta: { profile: 'official', release_id: releaseId, ruleset_version: 'rules-v1',
      coverage_note: 'Synthetic camera fixture.', next_cursor: null, total_count: 1 },
  } }));
  await page.route(url => url.pathname === '/api/v2/discovery/facets', route => route.fulfill({ status: 200, json: {
    api_version: 'v2', data: { dimensions: {} }, meta: { profile: 'official', release_id: releaseId, ruleset_version: 'rules-v1' },
  } }));
  return requests;
}

async function clickCameraFixturePin(page: import('@playwright/test').Page) {
  await expect(page.getByText('No records match this search and these filters.', { exact: true })).toBeHidden();
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getLayer('approx-reference-pins') && map.queryRenderedFeatures({ layers: ['approx-reference-pins'] }).length > 0;
  })).toBe(true);
  const point = await page.evaluate(coordinate => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const pixel = map.project(coordinate), box = map.getCanvas().getBoundingClientRect();
    return { x: box.x + pixel.x, y: box.y + pixel.y - 14 };
  }, cameraFixturePoint);
  await page.mouse.click(point.x, point.y);
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${cameraFixtureId}`);
}

async function mockCameraRaster(page: import('@playwright/test').Page) {
  const body = Buffer.from(await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 256;
    const context = canvas.getContext('2d')!; context.fillStyle = '#252b28'; context.fillRect(0, 0, 256, 256);
    return canvas.toDataURL('image/png').split(',')[1]!;
  }), 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ contentType: 'image/png', body }));
  await page.route('https://server.arcgisonline.com/**', route => route.fulfill({ contentType: 'image/png', body }));
  return body;
}

// These tests exercise the renderer, not external imagery availability. Tests
// that deliberately delay or fail tiles register their own routes afterward.
test.beforeEach(async ({ page }) => { await mockCameraRaster(page); });

test('a reloaded public map reports its cached projection and uses one loading message', async ({ page }) => {
  const requests = await installPublicCameraFixture(page); await mockCameraRaster(page);
  await page.addInitScript(() => {
    const samples: string[] = []; (window as any).__syntheticLoadingLabels = samples;
    new MutationObserver(() => {
      const label = document.querySelector('.startup-status > span')?.textContent;
      if (label && samples.at(-1) !== label) samples.push(label);
    }).observe(document, { childList: true, subtree: true, characterData: true });
  });
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.95&lon=4.45&z=13');
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.isSourceLoaded('locations'));
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
  await page.getByRole('button', { name: 'Close More tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  const renderer = page.locator('#map-diagnostics summary').filter({ hasText: 'Renderer & timing' });
  await renderer.click();
  const metric = (name: string) => page.locator('#map-diagnostics dt').filter({ hasText: new RegExp(`^${name}$`) }).locator('..').locator('dd');
  await expect(metric('Cache')).toHaveText(/^(miss|hit) · 1 entries$/);
  const decoded = await metric('Decoded projection').textContent();
  expect(decoded).not.toBe('Unavailable');
  const feedRequests = requests.feeds;
  await page.reload();
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.isSourceLoaded('locations'));
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
  await page.getByRole('button', { name: 'Close More tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click(); await renderer.click();
  await expect(metric('Cache')).toHaveText(/^hit · 1 entries$/);
  await expect(metric('Decoded projection')).toHaveText(decoded!);
  expect(requests.feeds).toBe(feedRequests);
  const labels = await page.evaluate(() => (window as any).__syntheticLoadingLabels as string[]);
  expect(labels.length).toBeGreaterThan(0);
  expect(labels.every(label => !label.includes('step '))).toBe(true);
  expect(labels.every(label => ['Loading map…', 'Restoring cached map…', 'First time loading. This may take a while…'].includes(label))).toBe(true);
});

test('world preload controls change actual cached zoom coverage, budget, layers and clear/reset behavior', async ({ page }) => {
  test.setTimeout(60_000);
  await installPublicCameraFixture(page); await mockCameraRaster(page);
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.95&lon=4.45&z=13');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getSource('locations') && map.isSourceLoaded('locations') && map.isStyleLoaded();
  });
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
  await page.getByRole('button', { name: 'Close More tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  const debug = page.getByRole('complementary', { name: 'Debug menu', exact: true });
  await debug.locator('details.cache-controls > summary').click();
  const preload = debug.getByLabel('Preload world map', { exact: true });
  await preload.uncheck();
  await expect(debug.locator('#debug-world-zoom')).toBeDisabled();
  await debug.getByRole('button', { name: 'Clear world map cache', exact: true }).click();
  const stored = () => page.evaluate(async () => {
    const cache = await caches.open('uec-world-baseline-v1');
    return await Promise.all((await cache.keys()).map(async key => ({
      file: new URL(key.url).pathname.split('/').at(-1)!, bytes: (await (await cache.match(key))!.arrayBuffer()).byteLength,
    })));
  });
  await expect.poll(async () => (await stored()).length).toBe(0);
  // Switch to one complete world zoom before restoring full coverage.
  await preload.check();
  await debug.locator('#debug-world-zoom').press('Home');
  await debug.locator('#debug-world-budget').press('Home');
  await expect(debug.locator('#debug-world-zoom')).toHaveValue('0');
  await expect(debug.locator('#debug-world-budget')).toHaveValue('8');
  await expect.poll(async () => (await stored()).map(entry => entry.file).sort()).toEqual([
    'satellite-z0.b3a69656302c.bin', 'streets-z0.d8e74839926b.bin',
  ]);
  const low = await stored();
  expect(low.reduce((sum, entry) => sum + entry.bytes, 0)).toBe(5772 + 66795);
  await debug.locator('#debug-baseline-opacity').press('Home');
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return ['world-land', 'world-streets-land', 'world-streets-water'].map(id => map.getPaintProperty(id, 'fill-opacity'));
  })).toEqual([0, 0, 0]);
  await debug.getByRole('button', { name: 'Reset cache controls', exact: true }).click();
  await expect(debug.locator('#debug-world-zoom')).toHaveValue('5');
  await expect(debug.locator('#debug-world-budget')).toHaveValue('24');
  await expect.poll(async () => (await stored()).length, { timeout: 20_000 }).toBe(12);
  expect((await stored()).reduce((sum, entry) => sum + entry.bytes, 0)).toBeLessThanOrEqual(24 * 1048576);
  await preload.uncheck();
  await debug.getByRole('button', { name: 'Clear world map cache', exact: true }).click();
  await expect.poll(async () => (await stored()).length).toBe(0);
  const original = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return { tiles: map.getStyle().sources.base.tiles[0], opacity: map.getPaintProperty('world-streets-land', 'fill-opacity') };
  });
  expect(original.tiles).toContain('openstreetmap.org'); expect(original.opacity).toBe(1);
});

for (const viewport of [{ width: 1280, height: 720 }, { width: 390, height: 844 }]) {
  test(`debug header and close remain unobscured with collapsed search at ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await installPublicCameraFixture(page); await mockCameraRaster(page);
    await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.95&lon=4.45&z=13');
    await expect(page.getByRole('button', { name: /Search map/ })).toBeVisible();
    await page.getByRole('button', { name: 'More tools', exact: true }).click();
    await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
    await page.getByRole('button', { name: 'Close More tools', exact: true }).click();
    await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
    await expect(page.getByRole('button', { name: /Search map/ })).toBeHidden();
    for (const target of [page.locator('#map-diagnostics > header strong'), page.getByRole('button', { name: 'Close debug menu', exact: true })]) {
      await expect(target).toBeVisible();
      expect(await target.evaluate(node => {
        const box = node.getBoundingClientRect();
        const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
        return hit === node || Boolean(hit && node.contains(hit));
      })).toBe(true);
    }
    await page.screenshot({ path: testInfo.outputPath(`debug-header-${viewport.width}.png`) });
    await page.getByRole('button', { name: 'Close debug menu', exact: true }).click();
    await expect(page.getByRole('button', { name: /Search map/ })).toBeVisible();
  });
}

test('raster detail for common geographic points stays stable across fixed-camera bearings', async ({ page }) => {
  test.setTimeout(90_000);
  const levels: number[][] = [];
  const points = [[4.45, 50.95], [4.18, 50.95], [4.45, 50.72]];
  await page.setViewportSize({ width: 1280, height: 720 });
  await installPublicCameraFixture(page); await mockCameraRaster(page); await installTerrainFixture(page);
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.95&lon=4.45&z=8.3&pitch=45');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getLayer('clusters') && map.isSourceLoaded('base') && map.isSourceLoaded('mapterhorn-terrain');
  });
  // Rotate one live map, as a user does, rather than paying for four complete
  // WebGL/worker start-ups and shutdowns inside one test timeout.
  for (const bearing of [0, 90, 180, 270]) {
      await page.evaluate(value => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ bearing: value }), bearing);
      // Reload the style after the viewport has its final size. Initial hidden
      // container requests can otherwise conceal the steady-state LOD choice.
      const tiles = await page.evaluate(async () => {
        const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, current = map.getStyle();
        const seen: Array<{ z: number; x: number; y: number }> = [];
        let finish: () => void;
        const loaded = new Promise<void>((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error('Base raster did not finish loading')), 15_000);
          finish = () => { clearTimeout(timeout); resolve(); };
        });
        const record = (event: any) => {
          if (event.sourceId === 'base' && event.coord?.canonical) {
            const { z, x, y } = event.coord.canonical; seen.push({ z, x, y });
            if (map.isSourceLoaded('base')) finish();
          }
        };
        map.on('sourcedata', record);
        map.setStyle({ version: 8, sources: { base: current.sources.base, transport: current.sources.transport },
          layers: current.layers.filter((layer: { id: string }) => layer.id === 'base' || layer.id === 'transport') }, { diff: false });
        try { await loaded; return seen; } finally { map.off('sourcedata', record); }
      });
      expect(await page.evaluate(coordinates => {
        const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, canvas = map.getCanvas();
        return coordinates.every(coordinate => { const point = map.project(coordinate); return point.x > 0 && point.x < canvas.clientWidth && point.y > 0 && point.y < canvas.clientHeight; });
      }, points)).toBe(true);
      levels.push(points.map(([longitude, latitude]) => Math.max(...tiles.filter(tile => {
        const x = Math.floor((longitude! + 180) / 360 * 2 ** tile.z);
        const y = Math.floor((1 - Math.asinh(Math.tan(latitude! * Math.PI / 180)) / Math.PI) / 2 * 2 ** tile.z);
        return tile.x === x && tile.y === y;
      }).map(tile => tile.z))));
  }
  expect(levels.every(level => level.every(Number.isFinite))).toBe(true);
  expect(levels, 'Actual raster tile zoom at common points stays at camera zoom plus the 256px tile offset').toEqual(Array.from({ length: 4 }, () => points.map(() => 9)));
});

test('bearing rotation keeps common-area cluster memberships at one level without rebuilding the index', async ({ page }) => {
  test.setTimeout(60_000);
  await installPublicCameraFixture(page); await mockCameraRaster(page); await installTerrainFixture(page);
  let feeds = 0;
  const features = Array.from({ length: 3000 }, (_, i) => {
    const id = `123e4567-e89b-42d3-a456-${i.toString(16).padStart(12, '0')}`;
    return { type: 'Feature', id, geometry: { type: 'Point', coordinates: [4.45 + (i % 60 - 30) * .03, 50.95 + (Math.floor(i / 60) - 25) * .03] },
      properties: { facility_id: id, source_id: 'fixture.source', category_key: 'slaughter', category_keys: ['slaughter'], precision: 'source_reported', weight: 1 } };
  });
  await page.route(url => url.pathname === '/api/v2/map/feed', route => { feeds++; return route.fulfill({ json: {
    api_version: 'v2', data: { type: 'FeatureCollection', features }, meta: { profile: 'official', release_id: 'synthetic-release-2026-09',
      manifest_sha256: 'a'.repeat(64), suppression_generation: 7, feature_count: 3000, public_record_count: 3000,
      unmapped_count: 0, release_label: 'Synthetic rotation fixture', dataset_version: 'synthetic-test' },
  } }); });
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.95&lon=4.45&z=8.3&pitch=45');
  await page.waitForFunction(() => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return map?.getLayer('clusters') && map.isSourceLoaded('locations'); });
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
  await page.getByRole('button', { name: 'Close More tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  await page.locator('#map-diagnostics summary').filter({ hasText: 'Renderer & timing' }).click();
  const counter = page.locator('#map-diagnostics dt').filter({ hasText: /^Index updates$/ }).locator('..').locator('dd');
  const updates = await counter.textContent();
  async function clustersAt(bearing: number) {
    await page.evaluate(bearing => new Promise<void>(resolve => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; map.once('idle', () => resolve()); map.jumpTo({ center: [4.45, 50.95], zoom: 8.3, pitch: 45, bearing }); map.triggerRepaint(); }), bearing);
    await page.waitForFunction(() => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return !map.isMoving() && map.isSourceLoaded('locations'); });
    return page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return [...new Set(map.queryRenderedFeatures({ layers: ['clusters'] }).filter((f: any) => Math.abs(f.geometry.coordinates[0] - 4.45) < .65 && Math.abs(f.geometry.coordinates[1] - 50.95) < .5)
        .map((f: any) => `${f.properties.cluster_id}:${f.properties.representedCount}`))].sort();
    });
  }
  const initial = await clustersAt(0); expect(initial.length).toBeGreaterThan(0);
  for (const bearing of [90, 180, 270, 0]) expect(await clustersAt(bearing)).toEqual(initial);
  await expect(counter).toHaveText(updates!); expect(feeds).toBe(1);
});

test('a 3D search flight centers a facility on sloping terrain after elevation tiles settle', async ({ page }) => {
  test.setTimeout(60_000);
  await installPublicCameraFixture(page); await mockCameraRaster(page);
  const dem = new Map<string, Buffer>();
  await page.route('https://tiles.mapterhorn.com/**', async route => {
    const path = new URL(route.request().url()).pathname.split('/').filter(Boolean), z = Number(path[0]), x = Number(path[1]);
    const key = `${z}/${x}`;
    let body = dem.get(key);
    if (!body) {
      const encoded = await page.evaluate(({ z, x }) => {
        const canvas = document.createElement('canvas'); canvas.width = canvas.height = 512;
        const context = canvas.getContext('2d')!, image = context.createImageData(512, 512);
        for (let px = 0; px < 512; px++) {
          const longitude = ((x + (px + .5) / 512) / 2 ** z) * 360 - 180;
          const elevation = Math.round(Math.min(1500, Math.max(0, (longitude - 4.2) * 4000)) * 256 + 32768 * 256);
          for (let py = 0; py < 512; py++) { const offset = (py * 512 + px) * 4; image.data[offset] = elevation >> 16; image.data[offset + 1] = elevation >> 8 & 255; image.data[offset + 2] = elevation & 255; image.data[offset + 3] = 255; }
        }
        context.putImageData(image, 0, 0); return canvas.toDataURL('image/png').split(',')[1]!;
      }, { z, x });
      body = Buffer.from(encoded, 'base64'); dem.set(key, body);
    }
    await route.fulfill({ contentType: 'image/png', body });
  });
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.95&lon=4.1&z=13&pitch=45&bearing=23');
  await page.waitForFunction(() => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return map?.getTerrain() && map.isSourceLoaded('mapterhorn-terrain') && map.getLayer('approx-reference-pins'); });
  await page.getByRole('button', { name: /Search map/ }).click();
  await page.locator('.record-list button').filter({ hasText: 'Synthetic camera fixture' }).click();
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${cameraFixtureId}`);
  await page.waitForFunction(() => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return !map.isMoving() && map.isSourceLoaded('mapterhorn-terrain'); });
  const result = await page.evaluate(coordinate => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, point = map.project(coordinate), canvas = map.getCanvas();
    return { drift: Math.hypot(point.x - canvas.clientWidth / 2, point.y - canvas.clientHeight / 2),
      elevation: map.queryTerrainElevation(coordinate), cameraElevation: map.getCenterElevation(), center: map.getCenter().toArray(), pitch: map.getPitch(), bearing: map.getBearing() };
  }, cameraFixturePoint);
  expect(result.elevation).toBeGreaterThan(900);
  expect(result.drift, JSON.stringify(result)).toBeLessThan(1);
  expect(result.pitch).toBe(45); expect(result.bearing).toBe(23);
  // A nearby pin click crosses a smaller elevation difference on the same slope.
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, center = [4.445, 50.95];
    map.jumpTo({ center, elevation: map.queryTerrainElevation(center) });
  });
  await page.keyboard.press('Escape');
  await clickCameraFixturePin(page);
  await expect.poll(() => page.evaluate(coordinate => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    if (map.isMoving() || !map.isSourceLoaded('mapterhorn-terrain')) return Infinity;
    const point = map.project(coordinate), canvas = map.getCanvas();
    return Math.hypot(point.x - canvas.clientWidth / 2, point.y - canvas.clientHeight / 2);
  }, cameraFixturePoint)).toBeLessThan(1);
});

test('cluster bodies render on cold and warm public maps through satellite, 3D and 2D', async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  await installPublicCameraFixture(page);
  await installTerrainFixture(page);
  const features = Array.from({ length: 3000 }, (_, i) => {
    const id = `123e4567-e89b-42d3-a456-${i.toString(16).padStart(12, '0')}`;
    return { type: 'Feature', id, geometry: { type: 'Point', coordinates: [4.45 + i % 60 * 0.0001, 50.95 + Math.floor(i / 60) * 0.0001] },
      properties: { facility_id: id, source_id: 'fixture.source', category_key: 'slaughter', category_keys: ['slaughter'], precision: 'source_reported', weight: 1 } };
  });
  await page.route(url => url.pathname === '/api/v2/map/feed', route => route.fulfill({ json: {
    api_version: 'v2', data: { type: 'FeatureCollection', features }, meta: { profile: 'official', release_id: 'synthetic-release-2026-09',
      manifest_sha256: 'a'.repeat(64), suppression_generation: 7, feature_count: 3000, public_record_count: 3000,
      unmapped_count: 0, release_label: 'Synthetic cluster fixture', dataset_version: 'synthetic-test' },
  } }));
  const raster = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 256;
    const context = canvas.getContext('2d')!; context.fillStyle = '#252b28'; context.fillRect(0, 0, 256, 256);
    return canvas.toDataURL('image/png').split(',')[1]!;
  });
  const tile = Buffer.from(raster, 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: tile }));
  await page.route('https://server.arcgisonline.com/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: tile }));
  async function expectClusterBody(stage: string) {
    await expect.poll(() => page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return Boolean(map?.getLayer('clusters') && map.queryRenderedFeatures({ layers: ['clusters'] }).some((f: any) => f.properties.representedCount === 3000));
    })).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`cluster-${stage}.png`) });
    expect(await page.evaluate(() => ['cluster-low', 'cluster-mid', 'cluster-high', 'cluster-very-high']
      .map(id => (window as any).__UEC_LOCAL_PREVIEW_MAP__.hasImage(id)))).toEqual([true, true, true, true]);
    const color = await page.evaluate(() => new Promise<number[]>(resolve => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      map.once('render', () => {
        const feature = map.queryRenderedFeatures({ layers: ['clusters'] }).find((f: any) => f.properties.representedCount === 3000);
        const point = map.project(feature.geometry.coordinates), canvas = map.getCanvas();
        const gl = canvas.getContext('webgl2'), pixel = new Uint8Array(4), ratio = canvas.width / canvas.clientWidth;
        // Sample the filled body below the count text, inside its 15 px radius.
        gl.readPixels(Math.round((point.x + 10) * ratio), Math.round(canvas.height - (point.y + 10) * ratio), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
        resolve(Array.from(pixel));
      });
      map.triggerRepaint();
    }));
    expect(color[0]! - color[1]!).toBeGreaterThan(30);
    expect(color[0]).toBeGreaterThan(100);
  }
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.9525&lon=4.453&z=8');
  await expectClusterBody('cold');
  await page.reload();
  await expectClusterBody('warm');
  const tools = page.getByRole('button', { name: 'More tools', exact: true }); await tools.click();
  await page.getByRole('navigation',{name:'Map navigation'}).getByRole('switch',{name:'Map style: Street',exact:true}).click();
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getStyle().sources.base.tiles[0]), { timeout: basemapHandoffTimeout }).toContain('World_Imagery');
  await expectClusterBody('satellite');
  const toggle = page.locator('.map-navigation .dimension-button'); await toggle.click();
  // The first tilt waits for the bounded DEM request before animating.
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPitch()), { timeout: 12_000 }).toBe(60);
  await expectClusterBody('3d'); await toggle.click();
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPitch())).toBe(0);
  await expectClusterBody('2d');
  await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, current = map.getStyle();
    const loaded = new Promise<void>(resolve => map.once('style.load', resolve));
    map.setStyle({ version: 8, sources: { base: current.sources.base, transport: current.sources.transport },
      layers: current.layers.filter((layer: { id: string }) => layer.id === 'base' || layer.id === 'transport') }, { diff: false });
    await loaded;
  });
  await expectClusterBody('style-reload');
});

test('one approximate-pin click draws and dismisses its area while raster tiles remain pending', async ({ page }) => {
  test.setTimeout(45_000);
  await installPublicCameraFixture(page);
  const tile = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/F2sAAAAASUVORK5CYII=', 'base64');
  let hold = false, pending = 0, release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('https://tile.openstreetmap.org/**', async route => {
    if (hold) { pending++; await gate; }
    await route.fulfill({ status: 200, contentType: 'image/png', body: tile });
  });
  try {
    await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.95&lon=4.45&z=13');
    await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.isStyleLoaded());
    await expect.poll(() => page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return Boolean(map?.getLayer('approx-reference-pins') && map.queryRenderedFeatures({ layers: ['approx-reference-pins'] }).length);
    })).toBe(true);
    hold = true;
    await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ zoom: 16 }));
    await expect.poll(() => pending).toBeGreaterThan(0);
    await clickCameraFixturePin(page);
    await expect.poll(() => page.evaluate(async () => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return { styleReady: map.isStyleLoaded(), areas: (await map.getSource('approximate-reference-area').getData()).features.length };
    })).toEqual({ styleReady: false, areas: 1 });
    await page.keyboard.press('Escape');
    await expect.poll(() => page.evaluate(async () => (await (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('approximate-reference-area').getData()).features.length)).toBe(0);
  } finally { release(); }
});

test('delayed high-elevation terrain keeps the selected geographic focus anchored through 3D and 2D', async ({ page }) => {
  test.setTimeout(60_000);
  await installPublicCameraFixture(page);
  const tile = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/F2sAAAAASUVORK5CYII=', 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: tile }));
  const elevationTile = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 512;
    const context = canvas.getContext('2d')!;
    context.fillStyle = 'rgb(131,232,0)'; // Terrarium: exactly 1,000 metres.
    context.fillRect(0, 0, 512, 512); return canvas.toDataURL('image/png').split(',')[1];
  });
  let demRequests = 0, release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('https://tiles.mapterhorn.com/**', async route => {
    demRequests++; await gate;
    await route.fulfill({ status: 200, contentType: 'image/png', body: Buffer.from(elevationTile!, 'base64') });
  });
  try {
    await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.95&lon=4.45&z=13&bearing=23');
    await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.isStyleLoaded());
    expect(demRequests).toBe(0);
    await clickCameraFixturePin(page);
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving())).toBe(false);
    const tools = page.getByRole('button', { name: 'More tools', exact: true }); await tools.click();
    const toggle = page.locator('.map-navigation .dimension-button');
    await toggle.click();
    await expect.poll(() => demRequests).toBeGreaterThan(0);
    // Load elevation while overhead, before tilting, so no late height jump is visible.
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving())).toBe(false);
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPitch())).toBe(0);
    release();
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPitch())).toBe(60);
    const camera = await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return { zoom: map.getZoom(), bearing: map.getBearing() };
    });
    const assertFocus = async (bearing = camera.bearing) => {
      await expect.poll(() => page.evaluate(({ coordinate, previous }) => {
        const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, pixel = map.project(coordinate), box = map.getCanvas().getBoundingClientRect();
        return Math.max(Math.abs(pixel.x - box.width / 2), Math.abs(pixel.y - box.height / 2), Math.abs(map.getZoom() - previous.zoom), Math.abs(map.getBearing() - previous.bearing));
      }, { coordinate: cameraFixturePoint, previous: { ...camera, bearing } })).toBeLessThan(1);
    };
    await assertFocus(); await toggle.click();
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPitch())).toBe(0);
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getTerrain())).toMatchObject({ source: 'mapterhorn-terrain', exaggeration: 1 });
    await assertFocus(0); await toggle.click();
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPitch())).toBe(60);
    await assertFocus(0);
  } finally { release(); }
});

test('returning from About revalidates the release and reuses the live canvas and cluster index', async ({ page }) => {
  test.setTimeout(45_000);
  const requests = await installPublicCameraFixture(page);
  const tile = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/F2sAAAAASUVORK5CYII=', 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: tile }));
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.95&lon=4.45&z=13&bearing=23');
  await page.getByRole('button', { name: /Search map/ }).click();
  await page.locator('.record-list button').filter({ hasText: 'Synthetic camera fixture' }).click();
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${cameraFixtureId}`);
  const tools = page.getByRole('button', { name: 'More tools', exact: true }); await tools.click();
  await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
  await page.getByRole('button', { name: 'Close More tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  await page.locator('#map-diagnostics summary').filter({ hasText: 'Renderer & timing' }).click();
  const counter = page.locator('#map-diagnostics dt').filter({ hasText: /^Index updates$/ }).locator('..').locator('dd');
  await expect(counter).toHaveText(/^\d+$/);
  const indexUpdates = await counter.textContent(), manifestRequests = requests.manifests, feedRequests = requests.feeds;
  const canvas = await page.locator('.maplibregl-canvas').elementHandle();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'About', exact: true }).click();
  await expect(page).toHaveURL(/#\/about/);
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty', exact: true }).first()).toBeVisible();
  await page.goBack();
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await expect.poll(() => requests.manifests).toBeGreaterThan(manifestRequests);
  expect(await canvas!.evaluate(node => node === document.querySelector('.maplibregl-canvas'))).toBe(true);
  await expect(counter).toHaveText(indexUpdates!);
  expect(requests.feeds).toBe(feedRequests);
  expect(new URL(page.url()).hash).toContain(`selected=${cameraFixtureId}`);
  expect(new URL(page.url()).hash).toContain('bearing=23');
});

async function installTerrainFixture(page: import('@playwright/test').Page) {
  const tileData = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 512;
    const context = canvas.getContext('2d')!;
    // Terrarium RGB 128/128/128 represents a flat elevation near zero metres.
    context.fillStyle = 'rgb(128, 128, 128)';
    context.fillRect(0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/webp').split(',')[1];
  });
  const body = Buffer.from(tileData, 'base64');
  await page.route('https://tiles.mapterhorn.com/**', route => route.fulfill({ status: 200, contentType: 'image/webp', body }));
}

test('camera tilt, map style, and URL state preserve the map view without compass controls', async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  const tileData = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 256;
    const context = canvas.getContext('2d')!;
    context.fillStyle = '#252b28';
    context.fillRect(0, 0, 256, 256);
    context.strokeStyle = '#303834';
    context.lineWidth = 1;
    for (const offset of [64, 128, 192]) {
      context.beginPath(); context.moveTo(offset, 0); context.lineTo(offset, 256); context.stroke();
      context.beginPath(); context.moveTo(0, offset); context.lineTo(256, offset); context.stroke();
    }
    return canvas.toDataURL('image/png').split(',')[1];
  });
  const pixel = Buffer.from(tileData, 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: pixel }));
  await page.route('**/World_Imagery/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: pixel }));
  await installTerrainFixture(page);
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4&pitch=31&bearing=24');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getLayer('clusters');
  });
  const map = page.getByLabel('Map showing records');
  const controls = page.getByRole('navigation', { name:'Map navigation' });
  const viewToggle = controls.locator('.dimension-button');
  await expect(controls).toBeVisible();
  await expect(map.locator('.maplibregl-ctrl-compass')).toHaveCount(0);
  await expect(viewToggle).toHaveText('3D');
  await expect(viewToggle).toHaveAttribute('aria-pressed', 'true');
  await expect(viewToggle).toHaveAttribute('title', 'Right-drag to tilt and rotate');
  await page.screenshot({ path: testInfo.outputPath('map-controls-desktop.png') });
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(31);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getBearing())).toBe(24);
  const nav = page.getByRole('navigation', { name: 'Primary' });
  const aboutHref = await nav.getByRole('link', { name:'About', exact:true }).getAttribute('href');
  const hrefParams = new URLSearchParams(new URLSearchParams(aboutHref?.split('?')[1]).get('map')?.split('?')[1]);
  expect(hrefParams.get('pitch')).toBe('31');
  expect(hrefParams.get('bearing')).toBe('24');
  const mapHrefParams = new URLSearchParams((await nav.getByRole('link', { name: 'Map', exact: true }).getAttribute('href'))?.split('?')[1]);
  expect(mapHrefParams.get('pitch')).toBe('31');
  expect(mapHrefParams.get('bearing')).toBe('24');

  await viewToggle.click();
  await expect(viewToggle).toHaveText('2D');
  await expect(viewToggle).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(() => new URL(page.url()).hash).not.toMatch(/pitch=/);
  await expect.poll(() => new URL(page.url()).hash).not.toMatch(/bearing=/);
  await viewToggle.click();
  await expect(viewToggle).toHaveText('3D');
  await expect(viewToggle).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => new URL(page.url()).hash).toContain('pitch=60');
  await expect.poll(() => new URL(page.url()).hash).not.toMatch(/bearing=/);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(60);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getTerrain())).toMatchObject({ source: 'mapterhorn-terrain', exaggeration: 1 });

  const mapStyle = controls.getByRole('switch', { name:'Map style: Street', exact:true });
  await expect(mapStyle).toContainText('Street');
  await expect(mapStyle).toHaveAttribute('aria-checked','false');
  const mapState = await page.evaluate(() => {
    const instance = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const center = instance.getCenter();
    return { lat: Number(center.lat.toFixed(5)), lon: Number(center.lng.toFixed(5)), zoom: instance.getZoom() };
  });
  await mapStyle.click();
  const satelliteSwitch = controls.getByRole('switch',{name:'Map style: Satellite',exact:true});
  await expect(satelliteSwitch).toHaveAttribute('aria-checked','true');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0]), { timeout: basemapHandoffTimeout }).toContain('World_Imagery');
  await expect.poll(() => page.evaluate(() => {
    const instance = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return [instance.getPitch(), instance.getBearing(), instance.getZoom(), Boolean(instance.getLayer('clusters'))];
  })).toEqual([60, 0, mapState.zoom, true]);
  await satelliteSwitch.click();
  await expect(mapStyle).toHaveAttribute('aria-checked','false');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0]), { timeout: basemapHandoffTimeout }).toContain('tile.openstreetmap.org');
});

test('flat camera URLs stay compact and the camera control remains usable on touch layouts', async ({ page }, testInfo) => {
  await installTerrainFixture(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./#/map?f1a=field&scenario=dense');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getLayer('clusters');
  });
  const controls = page.getByRole('navigation', { name:'Map navigation' });
  const viewToggle = controls.locator('.dimension-button');
  await expect(controls).toBeVisible();
  await expect(viewToggle).toBeVisible();
  await expect(viewToggle).toHaveText('2D');
  await expect(viewToggle).toHaveAttribute('aria-pressed', 'false');
  await expect(viewToggle).toHaveAttribute('aria-describedby', 'map-camera-help');
  await page.screenshot({ path: testInfo.outputPath('map-controls-mobile.png') });
  await viewToggle.click();
  await expect(viewToggle).toHaveText('3D');
  await expect(viewToggle).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => new URL(page.url()).hash).toContain('pitch=60');
});

test('map tools toggle 3D and preserve accessible gesture guidance without compass controls', async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  await installTerrainFixture(page);
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getLayer('clusters');
  });
  const controls = page.getByRole('navigation', { name:'Map navigation' });
  const viewToggle = controls.locator('.dimension-button');
  const styleSelect = controls.getByRole('switch', { name:'Map style: Street', exact:true });
  await expect(controls.locator('#map-camera-help')).toContainText('Right-drag to tilt and rotate');
  await expect(page.locator('.maplibregl-ctrl-compass')).toHaveCount(0);
  await expect(styleSelect).toContainText('Street');
  await expect(viewToggle).toHaveText('2D');
  await expect(controls.locator('#map-camera-help')).toHaveClass(/sr-only/);
  const rowTops = await Promise.all([styleSelect.boundingBox(), viewToggle.boundingBox()]);
  expect(rowTops.every(Boolean)).toBe(true);
  const rowCenters = rowTops.map(box => box!.y + box!.height / 2);
  expect(Math.max(...rowCenters) - Math.min(...rowCenters)).toBeLessThan(2);
  await viewToggle.click();
  await expect(viewToggle).toHaveText('3D');
  await expect(viewToggle).toHaveAttribute('title', 'Right-drag to tilt and rotate');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.getPitch() === 60 && !map.isMoving();
  });
  await page.screenshot({ path: testInfo.outputPath('map-controls-desktop.png') });
  // The toggle above establishes 60°, which is also the renderer's maximum.
  // Start the separate native gesture check below that limit so an upward
  // right-drag can change both pitch and bearing instead of clamping pitch.
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ pitch:35 }));
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPitch())).toBe(35);
  const before = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return { pitch: map.getPitch(), bearing: map.getBearing(), tileCacheZoomLevels: map._maxTileCacheZoomLevels };
  });
  expect(before.tileCacheZoomLevels).toBe(6);
  const canvas = await page.locator('.maplibregl-canvas').boundingBox();
  expect(canvas).not.toBeNull();
  // The joined results surface overlays the center-left; gesture on uncovered map.
  await page.mouse.move(canvas!.x + canvas!.width * 0.8, canvas!.y + canvas!.height * 0.6);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(canvas!.x + canvas!.width * 0.94, canvas!.y + canvas!.height * 0.55, { steps: 8 });
  await page.mouse.up({ button: 'right' });
  await expect.poll(() => page.evaluate((initial: { pitch: number; bearing: number }) => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return Math.abs(map.getPitch() - initial.pitch) > 1 && Math.abs(map.getBearing() - initial.bearing) > 1;
  }, before)).toBe(true);
  await expect.poll(() => new URL(page.url()).hash).toMatch(/pitch=[^&]+.*bearing=[^&]+/);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(controls).toBeVisible();
  await expect(viewToggle).toBeVisible();
  // The style selector and 2D/3D toggle stay aligned within the Tools menu.
  const mobileRowTops = await Promise.all([
    styleSelect.boundingBox(),
    viewToggle.boundingBox(),
  ]);
  expect(mobileRowTops.every(Boolean)).toBe(true);
  const mobileRowCenters = mobileRowTops.map(box => box!.y + box!.height / 2);
  expect(Math.max(...mobileRowCenters) - Math.min(...mobileRowCenters)).toBeLessThan(2);
  const toolbar = await page.locator('.map-toolbar').boundingBox();
  expect(toolbar!.x + toolbar!.width/2).toBeCloseTo(195,0);
  await expect(controls.locator('#map-camera-help')).toHaveClass(/sr-only/);
  await expect(viewToggle).toHaveAttribute('aria-describedby', 'map-camera-help');
  await expect(controls.locator('#map-camera-help')).toContainText('Right-drag to tilt and rotate');
  await expect(page.locator('.maplibregl-ctrl-compass')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('map-controls-mobile.png') });
});

test('selecting a map pin gently centres the camera on that record', async ({ page }) => {
  const record = labRecords.find(record => record.id === 'dense-exact-0-0')!;
  const point = [record.longitude!, record.latitude!] as [number, number];
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4');
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getLayer('exact-pins')))).toBe(true);
  await page.evaluate(({ point, id }) => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const feature = {
      type: 'Feature', geometry: { type: 'Point', coordinates: point },
      properties: { id }, layer: { id: 'exact-pins' },
    };
    map.queryRenderedFeatures = (_point: unknown, options: { layers?: string[] } = {}) =>
      options.layers?.includes('exact-pins') ? [feature] : [];
    map.fire('click', { point: { x: 20, y: 20 }, lngLat: { lng: point[0], lat: point[1] }, originalEvent: new MouseEvent('click') });
  }, { point, id: record.id });
  await expect.poll(() => page.evaluate(() => {
    const center = (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getCenter();
    return center ? [Number(center.lng.toFixed(1)), Number(center.lat.toFixed(1))] : null;
  })).toEqual(point.map(value => Number(value.toFixed(1))));
});

test('a shared basemap change during map startup waits for the style', async ({ page }) => {
  await installTerrainFixture(page);
  await page.addInitScript(() => {
    let current: any;
    const errors: string[] = [];
    (window as any).__earlyBasemapErrors = errors;
    Object.defineProperty(window, '__UEC_LOCAL_PREVIEW_MAP__', {
      configurable: true,
      get: () => current,
      set: instance => {
        current = instance;
        if (!instance) return;
        const addSource = instance.addSource;
        instance.addSource = function (...args: any[]) {
          try { return addSource.apply(this, args); }
          catch (error) { errors.push(`${args[0]}: ${error instanceof Error ? error.message : String(error)}`); throw error; }
        };
        queueMicrotask(() => { location.hash = '#/map?f1a=field&scenario=dense&basemap=satellite&lat=40.7&lon=-73.9&z=8&pitch=20&selected=dense-exact-0-0'; });
      },
    });
  });
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0]), { timeout: basemapHandoffTimeout }).toContain('World_Imagery');
  expect(await page.evaluate(() => (window as any).__earlyBasemapErrors)).toEqual([]);
  await expect(page).toHaveURL(/basemap=satellite/);
});

test('closing details during a pending basemap switch preserves the requested style', async ({ page }) => {
  const tile = await mockCameraRaster(page);
  await installTerrainFixture(page);
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getLayer('clusters') && map.isSourceLoaded('base');
  });
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/World_Imagery/**', async route => {
    await gate; await route.fulfill({ contentType: 'image/png', body: tile });
  });
  try {
    await page.goto('./#/map?f1a=field&scenario=dense&lat=40.7&lon=-73.9&z=8&basemap=satellite&selected=dense-exact-0-0');
    await expect(page.locator('.dossier')).toBeVisible();
    await expect(page.getByText('Loading Satellite imagery…', { exact: true })).toBeVisible();
    await page.evaluate(() => history.replaceState({ ...history.state, uecMapSelection: true }, '', location.href));
    await page.keyboard.press('Escape');
    await expect(page.locator('.dossier')).toBeHidden();
    await expect(page).toHaveURL(/basemap=satellite/);
    release();
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0]), { timeout: basemapHandoffTimeout }).toContain('World_Imagery');
    await expect(page).toHaveURL(/basemap=satellite/);
  } finally { release(); }
});

for (const dismissal of ['close button', 'Escape key', 'browser Back'] as const) {
  test(`dismissing a selected record with ${dismissal} preserves the selected camera and style`, async ({ page }) => {
    test.setTimeout(45_000);
    await installTerrainFixture(page);
    await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4&pitch=24&bearing=18');
    await page.locator('.map-surface').waitFor({ state: 'visible', timeout: 30_000 });
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(24);
    // Model a cold selected URL reached from a prior, wider map view. The real
    // MapLibre layer-click interaction is covered by the built-app acceptance.
    const selectedHash = '#/map?f1a=field&scenario=dense&lat=40.7&lon=-73.9&z=8&pitch=20&bearing=-17&basemap=satellite&selected=dense-exact-0-0';
    await page.goto(`./${selectedHash}`);
    await page.locator('.map-surface').waitFor({ state: 'visible', timeout: 30_000 });
    await expect(page.locator('.dossier')).toBeVisible();
    await page.waitForFunction(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return map.getStyle().sources.base.tiles[0].includes('World_Imagery') && !map.getSource('candidate-base') && map.isSourceLoaded('base');
    });
    await page.evaluate(() => history.replaceState({ ...history.state, uecMapSelection: true }, '', location.href));
    await expect.poll(() => page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return [Number(map.getCenter().lng.toFixed(1)), Number(map.getCenter().lat.toFixed(1))];
    })).toEqual([-73.9, 40.7]);
    const selectedCamera = await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const center = map.getCenter();
      return { center: [Number(center.lng.toFixed(4)), Number(center.lat.toFixed(4))], zoom: Number(map.getZoom().toFixed(2)), pitch: Number(map.getPitch().toFixed(1)), bearing: Number(map.getBearing().toFixed(1)) };
    });
    if (dismissal === 'close button') await page.getByRole('button', { name: 'Close record detail' }).click();
    else if (dismissal === 'Escape key') await page.keyboard.press('Escape');
    else await page.goBack();
    await expect(page.locator('.dossier')).toBeHidden();
    await expect.poll(() => page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const center = map.getCenter();
      return { center: [Number(center.lng.toFixed(4)), Number(center.lat.toFixed(4))], zoom: Number(map.getZoom().toFixed(1)), pitch: Math.round(map.getPitch()), bearing: Number(map.getBearing().toFixed(1)) };
    })).toEqual(selectedCamera);
    const hash = new URL(page.url()).hash;
    expect(hash).toContain('basemap=satellite');
    expect(hash).not.toContain('selected=');
    expect(hash).toContain('lat=40.7');
    expect(hash).toContain('lon=-73.9');
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0])).toContain('World_Imagery');
  });
}

test('a directly loaded selected URL survives reload and closes without restoring an older camera', async ({ page }) => {
  await installTerrainFixture(page);
  const selectedHash = '#/map?f1a=field&scenario=dense&lat=40.7&lon=-73.9&z=8&pitch=20&bearing=-17&basemap=satellite&selected=dense-exact-0-0';
  await page.goto(`./${selectedHash}`);
  await page.locator('.map-surface').waitFor({ state: 'visible', timeout: 30_000 });
  await expect(page.locator('.dossier')).toBeVisible();
  await page.reload();
  await page.locator('.map-surface').waitFor({ state: 'visible', timeout: 30_000 });
  await expect(page.locator('.dossier')).toBeVisible();
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const center = map.getCenter();
    return [Number(center.lng.toFixed(2)), Number(center.lat.toFixed(2)), Number(map.getZoom().toFixed(1)), Math.round(map.getPitch()), Number(map.getBearing().toFixed(1))];
  })).toEqual([-73.9, 40.7, 8, 20, -17]);
  await page.getByRole('button', { name: 'Close record detail' }).click();
  await expect(page.locator('.dossier')).toBeHidden();
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const center = map.getCenter();
    return [Number(center.lng.toFixed(2)), Number(center.lat.toFixed(2)), Number(map.getZoom().toFixed(1)), Math.round(map.getPitch()), Number(map.getBearing().toFixed(1))];
  })).toEqual([-73.9, 40.7, 8, 20, -17]);
  expect(new URL(page.url()).hash).toContain('basemap=satellite');
  expect(new URL(page.url()).hash).not.toContain('selected=');
});

test('cold shared 3D URLs restore terrain after a style reload and browser Back', async ({ page }) => {
  test.setTimeout(60_000);
  await installTerrainFixture(page);
  await installPublicCameraFixture(page);
  const tile = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/F2sAAAAASUVORK5CYII=', 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: tile }));
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.95&lon=4.45&z=13&pitch=45&bearing=18');
  const map = page.getByLabel('Map showing records');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(45);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getTerrain())).toMatchObject({ source: 'mapterhorn-terrain', exaggeration: 1 });
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getSource('mapterhorn-terrain')))).toBe(true);

  await page.evaluate(async () => {
    const instance = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const current = instance.getStyle();
    const style = {
      version: 8,
      sources: { base: current.sources.base, transport: current.sources.transport },
      layers: current.layers.filter((layer: { id: string }) => layer.id === 'base' || layer.id === 'transport'),
    };
    const loaded = new Promise<void>(resolve => instance.once('style.load', resolve));
    instance.setStyle(style, { diff: false });
    await loaded;
  });
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getTerrain())).toMatchObject({ source: 'mapterhorn-terrain', exaggeration: 1 });
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getSource('mapterhorn-terrain')))).toBe(true);

  const aboutHref = await page.getByRole('navigation', { name:'Primary' }).getByRole('link', { name:'About', exact:true }).getAttribute('href');
  const params = new URLSearchParams(new URLSearchParams(aboutHref?.split('?')[1]).get('map')?.split('?')[1]);
  expect(params.get('pitch')).toBe('45');
  expect(params.get('bearing')).toBe('18');
  expect(params.has('f1a')).toBe(false);
  expect(params.has('scenario')).toBe(false);
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'About', exact: true }).click();
  await expect(page).toHaveURL(/#\/about\?/);
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty', exact: true }).first()).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/pitch=45.*bearing=18/);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getTerrain()), { timeout: 15_000 }).toMatchObject({ source: 'mapterhorn-terrain', exaggeration: 1 });
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getSource('mapterhorn-terrain')))).toBe(true);
  await expect(map).toBeVisible();
});

test('flat maps do not request elevation and a DEM failure returns to a flat map', async ({ page }) => {
  let demRequests = 0;
  await page.route('https://tiles.mapterhorn.com/**', async route => {
    demRequests++;
    await route.abort();
  });
  await page.goto('./#/map?f1a=field&scenario=dense');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getLayer('clusters');
  });
  expect(demRequests).toBe(0);
  const tools = page.getByRole('button', { name: 'More tools', exact: true });
  await tools.click();
  await expect(tools).toHaveAttribute('aria-expanded', 'true');
  await page.locator('.map-navigation .dimension-button').click();
  await expect(page.getByRole('alert')).toContainText(/Terrain (tiles are unavailable|could not be loaded)/);
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return { pitch: map.getPitch(), terrain: map.getTerrain(), source: map.getSource('mapterhorn-terrain') };
  })).toMatchObject({ pitch: 0, terrain: null, source: undefined });
  expect(demRequests).toBeGreaterThan(0);
});
for (const heldStage of ['candidate','base'] as const) test(`rapid style toggles keep the latest Street choice during the ${heldStage} handoff`, async ({ page }) => {
  const requests=await installPublicCameraFixture(page);
  const tile=await mockCameraRaster(page);
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=50.95&lon=4.45&z=13');
  await page.waitForFunction(()=>{
    const map=(window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getLayer('clusters') && map.isSourceLoaded('base');
  });
  let imageRequests=0, release!:()=>void;
  const gate=new Promise<void>(resolve=>release=resolve);
  await page.route('**/World_Imagery/**',async route=>{
    imageRequests++;
    const mapHasBase=await page.evaluate(()=>String((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0]).includes('World_Imagery'));
    if(heldStage==='candidate' || mapHasBase) await gate;
    await route.fulfill({contentType:'image/png',body:tile}).catch(()=>{});
  });
  try {
    await page.getByRole('switch',{name:'Map style: Street',exact:true}).click();
    await expect.poll(()=>imageRequests).toBeGreaterThan(0);
    if(heldStage==='base') await expect.poll(()=>page.evaluate(()=>String((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0]))).toContain('World_Imagery');
    await page.getByRole('switch',{name:'Map style: Satellite',exact:true}).click();
    await expect(page.getByRole('switch',{name:'Map style: Street',exact:true})).toBeVisible();
    release();
    await expect(page.getByText('Loading Satellite imagery…',{exact:true})).toBeHidden();
    await expect.poll(()=>page.evaluate(()=>{
      const map=(window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return {base:String(map.getStyle().sources.base.tiles[0]),candidate:!!map.getSource('candidate-base')};
    })).toEqual({base:expect.stringContaining('tile.openstreetmap.org'),candidate:false});
    await expect(page.getByRole('switch',{name:'Map style: Street',exact:true})).toHaveAttribute('aria-checked','false');
    expect(new URL(page.url()).hash).not.toContain('basemap=satellite');
    expect(requests.feeds).toBe(1);
  } finally {release();}
});
