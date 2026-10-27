import { test, expect } from '@playwright/test';

test('map style exposes Street and Satellite only without refetching the native projection', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');
  test.setTimeout(90_000);
  let feedRequests = 0;
  page.on('request', request => {
    if (new URL(request.url()).pathname.endsWith('/map/feed')) feedRequests++;
  });
  await page.goto('/v2-preview/#/map');
  const mapStyle = page.locator('.map-navigation').getByRole('group', { name: 'Map style' });
  await expect(mapStyle.getByRole('switch', { name: 'Map style: Street', exact: true })).toHaveAttribute('aria-checked', 'false');
  await expect(mapStyle.getByRole('switch')).toHaveText('Street');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getLayer('clusters') && map.isSourceLoaded('locations');
  });
  const inspect = () => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const style = map.getStyle();
    const layers = style.layers.map((layer: { id: string }) => layer.id);
    return {
      tiles: style.sources.base.tiles,
      transport: layers.indexOf('transport'),
      overlays: ['clusters', 'aggregate-outer', 'approx-reference-points', 'source-coordinate-points'].map(id => layers.indexOf(id)),
      sourceLoaded: map.isSourceLoaded('locations'),
      saturation: map.getPaintProperty('base', 'raster-saturation'),
    };
  });
  const before = await inspect();
  expect(before.tiles[0]).toContain('tile.openstreetmap.org');
  expect(before.overlays.every((index: number) => index >= 0)).toBe(true);
  expect(before.sourceLoaded).toBe(true);
  await mapStyle.getByRole('switch').click();
  await expect(mapStyle.getByRole('switch', { name: 'Map style: Satellite', exact: true })).toHaveAttribute('aria-checked', 'true');
  await mapStyle.getByRole('switch').click();
  await expect(mapStyle.getByRole('switch', { name: 'Map style: Street', exact: true })).toHaveAttribute('aria-checked', 'false');
  expect(feedRequests).toBe(1);
});

test('unavailable satellite imagery leaves Street active', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');
  test.setTimeout(45_000);
  await page.route('**/World_Imagery/**', route => route.abort());
  await page.goto('/v2-preview/#/map');
  const mapStyle = page.locator('.map-navigation').getByRole('group', { name: 'Map style' });
  await expect(mapStyle.getByRole('switch', { name: 'Map style: Street', exact: true })).toHaveAttribute('aria-checked', 'false');
  await mapStyle.getByRole('switch').click();
  await expect(page.getByRole('alert').filter({ hasText: 'Satellite imagery is unavailable' })).toBeVisible({ timeout: 30_000 });
  await expect(mapStyle.getByRole('switch', { name: 'Map style: Street', exact: true })).toHaveAttribute('aria-checked', 'false');
  const tiles = await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getStyle().sources.base.tiles);
  expect(tiles[0]).toContain('tile.openstreetmap.org');
});
