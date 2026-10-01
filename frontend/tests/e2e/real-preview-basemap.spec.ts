import { test, expect } from '@playwright/test';

test('basemap control changes appearance while retaining the cached Supercluster projection', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');
  test.setTimeout(90_000);
  let feedRequests = 0;
  page.on('request', request => {
    if (new URL(request.url()).pathname.endsWith('/map/feed')) feedRequests++;
  });
  await page.goto('/#/map');
  const lens = page.getByRole('complementary', { name: 'Map lens' });
  await lens.getByRole('button', { name: /Map lens/ }).click();
  const street = lens.getByRole('button', { name: 'Street', exact: true });
  const muted = lens.getByRole('button', { name: 'Muted', exact: true });
  await expect(street).toHaveAttribute('aria-pressed', 'true');
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
  await muted.click();
  await expect(muted).toHaveAttribute('aria-pressed', 'true');
  const mutedState = await inspect();
  expect(mutedState.tiles).toEqual(before.tiles);
  expect(mutedState.overlays).toEqual(before.overlays);
  expect(mutedState.sourceLoaded).toBe(true);
  expect(mutedState.saturation).toBe(-1);
  await street.click();
  await expect(street).toHaveAttribute('aria-pressed', 'true', { timeout: 30_000 });
  const streetState = await inspect();
  expect(streetState.tiles[0]).toContain('tile.openstreetmap.org');
  expect(streetState.overlays).toEqual(before.overlays);
  expect(streetState.sourceLoaded).toBe(true);
  expect(streetState.saturation).toBe(0);
  expect(feedRequests).toBe(1);
});

test('unavailable satellite imagery leaves Street active', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');
  test.setTimeout(45_000);
  await page.route('**/World_Imagery/**', route => route.abort());
  await page.goto('/#/map');
  const lens = page.getByRole('complementary', { name: 'Map lens' });
  await lens.getByRole('button', { name: /Map lens/ }).click();
  const street = lens.getByRole('button', { name: 'Street', exact: true });
  const satellite = lens.getByRole('button', { name: 'Satellite', exact: true });
  await expect(street).toHaveAttribute('aria-pressed', 'true');
  await satellite.click();
  await expect(page.getByRole('alert').filter({ hasText: 'Satellite imagery is unavailable' })).toBeVisible({ timeout: 30_000 });
  await expect(street).toHaveAttribute('aria-pressed', 'true');
  await expect(satellite).toHaveAttribute('aria-pressed', 'false');
  const tiles = await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getStyle().sources.base.tiles);
  expect(tiles[0]).toContain('tile.openstreetmap.org');
});
