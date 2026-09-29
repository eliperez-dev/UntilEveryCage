import { test, expect } from '@playwright/test';

test('basemap control changes imagery while retaining native map overlays', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');
  test.setTimeout(90_000);
  await page.route('**/World_Imagery/**', async route => {
    await new Promise(resolve => setTimeout(resolve, 750));
    await route.continue();
  });
  await page.goto('/#/map');
  const street = page.getByRole('button', { name: 'Street', exact: true });
  const satellite = page.getByRole('button', { name: 'Satellite', exact: true });
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
      overlays: ['clusters', 'aggregate-outer', 'source-coordinate-points'].map(id => layers.indexOf(id)),
      sourceLoaded: map.isSourceLoaded('locations'),
    };
  });
  const before = await inspect();
  expect(before.tiles[0]).toContain('tile.openstreetmap.org');
  await satellite.click();
  const loading = page.getByRole('status').filter({ hasText: 'Loading Satellite imagery…' });
  await expect(loading).toBeVisible();
  await expect(satellite).toHaveAttribute('aria-pressed', 'true', { timeout: 30_000 });
  await expect(loading).toHaveCount(0);
  const after = await inspect();
  expect(after.tiles[0]).toContain('World_Imagery');
  expect(after.tiles).not.toEqual(before.tiles);
  expect(after.overlays.every((index: number) => index > after.transport)).toBe(true);
  expect(after.sourceLoaded).toBe(true);
  await street.click();
  await expect(street).toHaveAttribute('aria-pressed', 'true', { timeout: 30_000 });
  expect((await inspect()).tiles[0]).toContain('tile.openstreetmap.org');
});

test('unavailable satellite imagery leaves Street active', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');
  await page.route('**/World_Imagery/**', route => route.abort());
  await page.goto('/#/map');
  const street = page.getByRole('button', { name: 'Street', exact: true });
  const satellite = page.getByRole('button', { name: 'Satellite', exact: true });
  await expect(street).toHaveAttribute('aria-pressed', 'true');
  await satellite.click();
  await expect(page.getByRole('alert').filter({ hasText: 'Satellite imagery is unavailable' })).toBeVisible({ timeout: 15_000 });
  await expect(street).toHaveAttribute('aria-pressed', 'true');
  await expect(satellite).toHaveAttribute('aria-pressed', 'false');
  const tiles = await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getStyle().sources.base.tiles);
  expect(tiles[0]).toContain('tile.openstreetmap.org');
});
