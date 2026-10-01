import { expect, test } from '@playwright/test';

const MAP_LAYERS = ['clusters', 'source-coordinate-points', 'approx-reference-points'];

async function waitForProjection(page: import('@playwright/test').Page) {
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.isSourceLoaded('locations');
  }, undefined, { timeout: 90_000 });
}

test('private projection is downloaded once, then reused from the snapshot cache', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires the populated local real preview');
  test.setTimeout(180_000);
  await page.goto('/');
  await page.evaluate(async () => Promise.all((await caches.keys()).map(name => caches.delete(name))));
  let feedRequests = 0;
  page.on('request', request => {
    if (new URL(request.url()).pathname.endsWith('/map/feed')) feedRequests++;
  });

  const coldStart = performance.now();
  await page.goto('/#/map?f1a=field&lat=44.95&lon=9.87&z=6.1&list=closed');
  await waitForProjection(page);
  const coldMs = Math.round(performance.now() - coldStart);
  expect(feedRequests).toBe(1);

  const warmStart = performance.now();
  await page.reload();
  await waitForProjection(page);
  const warmMs = Math.round(performance.now() - warmStart);
  console.info(`UEC projection load: ${JSON.stringify({ coldMs, warmMs, feedRequests })}`);
  expect(feedRequests).toBe(1);
  expect(warmMs).toBeLessThan(coldMs);
  expect(await page.evaluate(async () => (await caches.keys()).includes('uec-private-map-projection-v1'))).toBe(true);
});

test('review fixtures retain organic hierarchy and uninterrupted western coverage', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires the populated local real preview');
  test.setTimeout(120_000);
  await page.goto('/#/map?f1a=field&lat=44.95&lon=9.87&z=6.1&list=closed');
  await waitForProjection(page);
  const result = await page.evaluate(async layers => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const sample = async (center: [number, number], zoom: number) => {
      map.jumpTo({ center, zoom });
      await new Promise<void>(resolve => map.once('idle', resolve));
      return map.queryRenderedFeatures({ layers });
    };
    const italy = await sample([9.87, 44.95], 6.1);
    const italyCounts = italy.filter((feature: any) => feature.properties?.cluster)
      .map((feature: any) => Number(feature.properties.representedCount));
    const west = [];
    for (const zoom of [2, 2.25, 2.5, 2.75, 3, 3.25]) {
      const features = await sample([-118, 38], zoom);
      west.push({ zoom, count: features.length, loaded: map.isSourceLoaded('locations') });
    }
    return { italyCounts, west };
  }, MAP_LAYERS);
  expect(result.italyCounts.length).toBeGreaterThan(5);
  expect(Math.max(...result.italyCounts)).toBeLessThan(3_000);
  expect(result.west.every(sample => sample.loaded && sample.count > 0)).toBe(true);
});

test('Belgium approximate references cluster low and resolve high', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires the populated local real preview');
  test.setTimeout(120_000);
  await page.goto('/#/map?f1a=field&lat=50.7&lon=4.6&z=6&list=closed');
  await waitForProjection(page);
  const result = await page.evaluate(async layers => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const sample = async (zoom: number) => {
      map.jumpTo({ center: [4.6, 50.7], zoom });
      await new Promise<void>(resolve => map.once('idle', resolve));
      return map.queryRenderedFeatures({ layers });
    };
    const low = await sample(6);
    const high = await sample(9);
    return {
      lowClusters: low.filter((feature: any) => feature.properties?.cluster).length,
      highClusters: high.filter((feature: any) => feature.properties?.cluster).length,
      highReferences: high.filter((feature: any) => feature.properties?.kind === 'reference').length,
    };
  }, MAP_LAYERS);
  expect(result.lowClusters).toBeGreaterThan(0);
  expect(result.highClusters).toBe(0);
  expect(result.highReferences).toBeGreaterThan(0);
});

test('camera movement remains client-local on desktop and mobile', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires the populated local real preview');
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/#/map?f1a=field&lat=44.95&lon=9.87&z=6.35&list=closed');
  await waitForProjection(page);
  const samples = await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const values = [];
    for (const action of ['pan-east', 'zoom-in', 'pan-west']) {
      const started = performance.now();
      const idle = new Promise<void>(resolve => map.once('idle', resolve));
      if (action === 'zoom-in') map.easeTo({ zoom: 6.85, duration: 180 });
      else map.panBy([action === 'pan-east' ? 120 : -120, 0], { duration: 180 });
      await new Promise<void>(resolve => map.once('moveend', resolve));
      const elapsed = Math.round(performance.now() - started);
      const visibleAtMoveend = map.queryRenderedFeatures({ layers: ['clusters', 'source-coordinate-points', 'approx-reference-points'] }).length;
      await idle;
      values.push({ elapsed, visibleAtMoveend, loadedAfterIdle: map.isSourceLoaded('locations') });
    }
    return values;
  });
  console.info(`UEC client-local mobile camera: ${JSON.stringify(samples)}`);
  expect(samples.every(sample => sample.loadedAfterIdle && sample.visibleAtMoveend > 0 && sample.elapsed < 1_000)).toBe(true);
  await expect(page.getByRole('button', { name: /Preview 38,633 mapped/ })).toBeVisible();
});
