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

test('approximate city markers and 3 km areas are derived from private MVT features', async ({ page }) => {
  requirePreview();
  test.setTimeout(90_000);
  await page.goto('/#/map?f1a=field&lat=50.7&lon=4.6&z=10&list=closed');
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
});

test('debug menu discloses MVT projection and offers honest visual controls', async ({ page }) => {
  requirePreview();
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
});
