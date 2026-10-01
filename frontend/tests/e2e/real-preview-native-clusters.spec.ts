import { expect, test } from '@playwright/test';

const requirePreview = () => test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');

test('reviewed map keeps cluster expansion on the cached MVT hierarchy', async ({ page }) => {
  requirePreview();
  test.setTimeout(90_000);
  const requests: string[] = [];
  page.on('request', request => requests.push(new URL(request.url()).pathname));
  const firstTile = page.waitForResponse(response =>
    /\/dev\/real-preview\/map\/tiles\/\d+\/\d+\/\d+/.test(new URL(response.url()).pathname) && response.status() === 200,
  );
  await page.goto('/#/map?f1a=field&lat=45&lon=5&z=2&list=closed');
  await firstTile;
  await expect(page.getByRole('button', { name: /Map features/ })).toHaveCount(0);
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getSource('preview-mvt') && map.getLayer('mvt-clusters') && map.isSourceLoaded('preview-mvt');
  });
  const point = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const feature = map.queryRenderedFeatures({ layers: ['mvt-clusters'] })
      .find((candidate: any) => Number.isFinite(Number(candidate.properties?.next_zoom)));
    if (!feature) return null;
    const pixel = map.project(feature.geometry.coordinates);
    return { x: pixel.x, y: pixel.y, zoom: map.getZoom() };
  });
  expect(point).not.toBeNull();
  const canvas = await page.locator('.maplibregl-canvas').boundingBox();
  expect(canvas).not.toBeNull();
  await page.mouse.click(canvas!.x + point!.x, canvas!.y + point!.y);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getZoom()))
    .toBeGreaterThan(point!.zoom + 0.1);
  expect(requests.some(path => path.includes('/map/tiles/'))).toBe(true);
  expect(requests.some(path => path.includes('/map/feed'))).toBe(false);
});

test('Belgium approximate markers and 3 km areas are derived from private MVT features and remain clickable', async ({ page }) => {
  requirePreview();
  test.setTimeout(90_000);
  const referenceRequests: string[] = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.includes('/references/')) referenceRequests.push(request.url());
  });
  await page.goto('/#/map?f1a=field&source=be.locations&lat=50.7&lon=4.6&z=8&list=closed');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.isSourceLoaded('preview-mvt') && map.getLayer('mvt-reference-center');
  }, undefined, { timeout: 60_000 });
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.queryRenderedFeatures({ layers: ['mvt-approx-reference-area'] }).length > 0;
  }, undefined, { timeout: 30_000 });
  const state = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return {
      cityFeatures: map.querySourceFeatures('preview-mvt', { sourceLayer: 'uec_preview' })
        .filter((feature: any) => feature.properties?.kind === 'city_reference').length,
      areas: map.queryRenderedFeatures({ layers: ['mvt-approx-reference-area'] }).length,
      centers: map.queryRenderedFeatures({ layers: ['mvt-reference-center'] }).length,
      properties: Object.keys(map.querySourceFeatures('preview-mvt', { sourceLayer: 'uec_preview' })[0]?.properties ?? {}),
    };
  });
  expect(state.cityFeatures).toBeGreaterThan(0);
  expect(state.areas).toBeGreaterThan(0);
  expect(state.centers).toBeGreaterThan(0);
  expect(state.properties).not.toContain('address');
  expect(state.properties).not.toContain('name');
  const marker = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const feature = map.queryRenderedFeatures({ layers: ['mvt-reference-center'] })[0];
    if (!feature) return null;
    const point = map.project(feature.geometry.coordinates);
    return { x: point.x, y: point.y };
  });
  expect(marker).not.toBeNull();
  const canvas = await page.locator('.maplibregl-canvas').boundingBox();
  expect(canvas).not.toBeNull();
  await page.mouse.click(canvas!.x + marker!.x, canvas!.y + marker!.y);
  await expect.poll(() => referenceRequests.length).toBeGreaterThan(0);
  await expect(page.getByText(/Approximate city location/)).toBeVisible();
});

test('Belgium approximate references join low-zoom clusters and resolve to blue references above cutoff', async ({ page }) => {
  requirePreview();
  test.setTimeout(120_000);
  await page.goto('/#/map?f1a=field&source=be.locations&lat=50.7&lon=4.6&z=2&list=closed');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.isSourceLoaded('preview-mvt') && map.getLayer('mvt-clusters');
  }, undefined, { timeout: 90_000 });
  const lowZoom = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const clusters = map.queryRenderedFeatures({ layers: ['mvt-clusters'] });
    const unique = new Map(clusters.map((feature: any) => [feature.properties.feature_key, Number(feature.properties.count)]));
    return { clusterCount: unique.size, represented: [...unique.values()].reduce((sum, count) => sum + count, 0),
      cityReferences: map.queryRenderedFeatures({ layers: ['mvt-reference-center'] }).length };
  });
  expect(lowZoom.clusterCount, 'Belgium reference candidates should enter the low-zoom cluster hierarchy').toBeGreaterThan(0);
  expect(lowZoom.represented).toBeGreaterThan(0);
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.setZoom(8));
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.isSourceLoaded('preview-mvt') && map.queryRenderedFeatures({ layers: ['mvt-reference-center'] }).length > 0;
  }, undefined, { timeout: 60_000 });
  const highZoom = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return { cityReferences: map.queryRenderedFeatures({ layers: ['mvt-reference-center'] }).length,
      areas: map.queryRenderedFeatures({ layers: ['mvt-approx-reference-area'] }).length,
      clusters: map.queryRenderedFeatures({ layers: ['mvt-clusters'] }).length };
  });
  expect(highZoom.cityReferences).toBeGreaterThan(0);
  expect(highZoom.areas).toBeGreaterThan(0);
});

test('dense FSIS clusters are organic, not aligned to the former 1/8-tile grid', async ({ page }) => {
  requirePreview();
  test.setTimeout(90_000);
  await page.goto('/#/map?f1a=field&source=us.fsis&lat=39.5&lon=-77&z=4&list=closed');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.isSourceLoaded('preview-mvt') && map.getLayer('mvt-clusters');
  }, undefined, { timeout: 90_000 });
  const distribution = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const scale = 512 * 2 ** map.getZoom();
    const features = map.queryRenderedFeatures({ layers: ['mvt-clusters'] });
    const offsets = features.map((feature: any) => {
      const [longitude, latitude] = feature.geometry.coordinates;
      const x = (longitude + 180) / 360 * scale;
      const radians = latitude * Math.PI / 180;
      const y = (1 - Math.asinh(Math.tan(radians)) / Math.PI) / 2 * scale;
      const distance = (value: number) => Math.min(value % 64, 64 - (value % 64));
      return Math.min(distance(x), distance(y));
    });
    return { count: features.length, nonGrid: offsets.filter((distance: number) => distance > 2).length,
      medianOffset: offsets.sort((a: number, b: number) => a - b)[Math.floor(offsets.length / 2)] ?? 0 };
  });
  expect(distribution.count).toBeGreaterThanOrEqual(8);
  expect(distribution.nonGrid).toBeGreaterThan(distribution.count * 0.75);
  expect(distribution.medianOffset).toBeGreaterThan(2);
});

test('pan and fractional zoom preserve MVT source/layers and never settle on an empty frame', async ({ page }) => {
  requirePreview();
  test.setTimeout(120_000);
  await page.goto('/#/map?f1a=field&source=us.fsis&lat=39.5&lon=-77&z=4&list=closed');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.isSourceLoaded('preview-mvt') && map.getLayer('mvt-clusters');
  }, undefined, { timeout: 90_000 });
  const result = await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const removals: string[] = [];
    const removeSource = map.removeSource.bind(map);
    const removeLayer = map.removeLayer.bind(map);
    const noteRemoval = (kind: string, id: string) => removals.push(`${kind}:${id}:${new Error().stack?.split('\n').slice(1, 4).join('|')}`);
    map.removeSource = (id: string) => { if (id === 'preview-mvt') noteRemoval('source', id); return removeSource(id); };
    map.removeLayer = (id: string) => { if (id.startsWith('mvt-')) noteRemoval('layer', id); return removeLayer(id); };
    const frames: { count: number; sourcePresent: boolean; layerPresent: boolean }[] = [];
    const sample = () => frames.push({
      count: map.queryRenderedFeatures({ layers: ['mvt-clusters', 'mvt-reference-center', 'mvt-source-coordinates'] }).length,
      sourcePresent: Boolean(map.getSource('preview-mvt')),
      layerPresent: Boolean(map.getLayer('mvt-clusters')),
    });
    map.on('render', sample);
    for (const camera of [
      { center: [-112, 39], zoom: 4.25 }, { center: [-105, 40], zoom: 4.75 },
      { center: [-98, 39], zoom: 5.25 }, { center: [-91, 38], zoom: 5.75 },
    ]) {
      map.jumpTo(camera);
      await new Promise<void>(resolve => map.once('idle', () => resolve()));
      sample();
    }
    map.off('render', sample);
    return { removals, frames,
      finalCount: map.queryRenderedFeatures({ layers: ['mvt-clusters', 'mvt-reference-center', 'mvt-source-coordinates'] }).length };
  });
  expect(result.removals).toEqual([]);
  expect(result.finalCount).toBeGreaterThan(0);
  expect(result.frames.length).toBeGreaterThan(0);
  expect(result.frames.every((frame: any) => frame.count > 0 && frame.sourcePresent && frame.layerPresent)).toBe(true);
});

test('western FSIS MVT coverage has no blank tiles through fractional zooms 2–3', async ({ page }) => {
  requirePreview();
  test.setTimeout(120_000);
  const tileCalls: string[] = [];
  page.on('response', async response => {
    if (response.url().includes('/map/tiles/')) tileCalls.push(`${response.status()} ${new URL(response.url()).pathname} bytes=${(await response.body().catch(() => new Uint8Array())).byteLength}`);
  });
  await page.goto('/#/map?f1a=field&source=us.fsis&lat=44.4363&lon=-88.8086&z=2&list=closed');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getSource('preview-mvt') && map.getLayer('mvt-clusters');
  }, undefined, { timeout: 60_000 });
  const results = await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const values = [];
    for (const zoom of [2, 2.25, 2.5, 2.75, 3, 3.25]) {
      map.setZoom(zoom);
      await new Promise<void>(resolve => map.once('idle', () => resolve()));
      const features = map.queryRenderedFeatures({ layers: ['mvt-clusters', 'mvt-source-coordinates'] });
      values.push({ zoom, count: features.length,
        west: features.filter((feature: any) => feature.geometry.coordinates[0] < -110).length });
    }
    return values;
  });
  expect(tileCalls.some(call => call.includes('/tiles/2/0/1') && call.includes('bytes=') && !call.endsWith('bytes=0')))
    .toBe(true);
  expect(results).toHaveLength(6);
  for (const result of results) {
    expect(result.count, `no map features at z=${result.zoom}`).toBeGreaterThan(0);
    expect(result.west, `no western FSIS features at z=${result.zoom}`).toBeGreaterThan(0);
  }
});

test('MVT cutoff controls preserve coverage and V1 pins render at pin zoom', async ({ page }) => {
  requirePreview();
  test.setTimeout(90_000);
  await page.goto('/#/map?f1a=field&source=us.fsis&lat=39.5&lon=-77&z=6&list=closed');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getLayer('mvt-source-coordinates');
  }, undefined, { timeout: 60_000 });
  await page.getByRole('button', { name: 'Debug menu' }).click();
  const cutoff = page.locator('#cluster-max-zoom');
  await expect(cutoff).toHaveValue('7.5');
  await cutoff.evaluate((element: HTMLInputElement) => {
    element.value = '4';
    element.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await expect.poll(async () => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.isSourceLoaded('preview-mvt') && map.queryRenderedFeatures({ layers: ['mvt-source-coordinates'] }).length;
  })).toBeGreaterThan(0);
  const pins = page.getByLabel('Use V1 facility pin PNG + shadow');
  await pins.check();
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.getLayoutProperty('mvt-v1-source-pins', 'visibility');
  })).toBe('visible');
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.queryRenderedFeatures({ layers: ['mvt-v1-source-pins'] }).length;
  })).toBeGreaterThan(0);
});

test('debug menu discloses MVT projection and offers honest visual controls', async ({ page }) => {
  requirePreview();
  test.setTimeout(90_000);
  await page.goto('/#/map?f1a=field&list=closed');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getLayer('mvt-clusters');
  }, undefined, { timeout: 60_000 });
  await page.getByRole('button', { name: 'Debug menu' }).click();
  await expect(page.getByText('Server-generated vector tiles')).toBeVisible();
  await expect(page.getByText(/Cluster membership and expansion levels come from the server-generated cached tile hierarchy/)).toBeVisible();
  await expect(page.getByLabel('Approx radius')).toHaveValue('3');
  await expect(page.getByLabel('Coordinate size')).toHaveValue('6.5');
  await expect(page.locator('#cluster-max-zoom')).toHaveValue('7.5');
  await expect(page.getByLabel('Use V1 facility pin PNG + shadow')).toBeVisible();
  await expect(page.getByRole('button', { name: /Map features/ })).toHaveCount(0);
});
