import { test, expect } from '@playwright/test';

test('basemap control changes appearance while retaining cached MVT overlays', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');
  test.setTimeout(90_000);
  await page.goto('/#/map');
  const lens = page.getByRole('complementary', { name: 'Map lens' });
  await lens.getByRole('button', { name: /Map lens/ }).click();
  const street = lens.getByRole('button', { name: 'Street', exact: true });
  const muted = lens.getByRole('button', { name: 'Muted', exact: true });
  await expect(street).toHaveAttribute('aria-pressed', 'true');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getLayer('mvt-clusters') && map.isSourceLoaded('preview-mvt');
  });
  const inspect = () => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const style = map.getStyle();
    const layers = style.layers.map((layer: { id: string }) => layer.id);
    return {
      tiles: style.sources.base.tiles,
      transport: layers.indexOf('transport'),
      overlays: ['mvt-clusters', 'mvt-reference-outer', 'mvt-source-coordinates'].map(id => layers.indexOf(id)),
      sourceLoaded: map.isSourceLoaded('preview-mvt'),
    };
  });
  const before = await inspect();
  expect(before.tiles[0]).toContain('tile.openstreetmap.org');
  await muted.click();
  await expect(muted).toHaveAttribute('aria-pressed', 'true');
  expect((await inspect()).tiles).toEqual(before.tiles);
  expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('base', 'raster-saturation'))).toBe(-1);
  await street.click();
  await expect(street).toHaveAttribute('aria-pressed', 'true', { timeout: 30_000 });
  expect((await inspect()).tiles[0]).toContain('tile.openstreetmap.org');
  expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('base', 'raster-saturation'))).toBe(0);
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
