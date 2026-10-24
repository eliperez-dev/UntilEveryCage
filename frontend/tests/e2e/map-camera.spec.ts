import { expect, test } from '@playwright/test';

test('camera tilt, compass reset, and URL state preserve the map view', async ({ page }) => {
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4&pitch=31&bearing=24');
  const map = page.getByLabel('Map showing records');
  const toggle = map.getByRole('button', { name: 'Return map to 2D' });
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(31);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getBearing())).toBe(24);

  await toggle.click();
  await expect(map.getByRole('button', { name: 'Show 3D terrain' })).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(() => new URL(page.url()).hash).not.toMatch(/pitch=/);
  await expect.poll(() => new URL(page.url()).hash).toContain('bearing=24');
  await map.getByRole('button', { name: 'Show 3D terrain' }).click();
  await expect.poll(() => new URL(page.url()).hash).toContain('pitch=45');
  await expect.poll(() => new URL(page.url()).hash).toContain('bearing=24');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(45);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getTerrain())).toMatchObject({ source: 'mapterhorn-terrain', exaggeration: 1 });

  const mapState = await page.evaluate(() => {
    const instance = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const center = instance.getCenter();
    return { lat: Number(center.lat.toFixed(5)), lon: Number(center.lng.toFixed(5)), zoom: instance.getZoom() };
  });
  const mapStyle = page.getByLabel('Map style');
  await mapStyle.selectOption('satellite');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0])).toContain('World_Imagery');
  await expect.poll(() => page.evaluate(() => {
    const instance = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return [instance.getPitch(), instance.getBearing(), instance.getZoom(), Boolean(instance.getLayer('clusters'))];
  })).toEqual([45, 24, mapState.zoom, true]);
  await mapStyle.selectOption('vector');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0])).toContain('tile.openstreetmap.org');
  await map.getByRole('button', { name: /reset north/i }).click();
  await expect.poll(() => page.evaluate(() => {
    const instance = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return [instance.getPitch(), instance.getBearing()];
  })).toEqual([0, 0]);
  await expect.poll(() => page.evaluate(() => {
    const instance = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const center = instance.getCenter();
    return [Number(center.lat.toFixed(5)), Number(center.lng.toFixed(5)), instance.getZoom()];
  })).toEqual([mapState.lat, mapState.lon, mapState.zoom]);
  await expect.poll(() => new URL(page.url()).hash).not.toMatch(/pitch=|bearing=/);
});

test('flat camera URLs stay compact and the camera control remains usable on touch layouts', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./#/map?f1a=field&scenario=dense');
  const toggle = page.getByRole('group', { name: 'Map camera' }).getByRole('button', { name: 'Show 3D terrain' });
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await toggle.click();
  await expect.poll(() => new URL(page.url()).hash).toContain('pitch=45');
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
  await page.getByRole('button', { name: 'Show 3D terrain' }).click();
  await expect(page.getByRole('alert')).toContainText(/Terrain (tiles are unavailable|could not be loaded)/);
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return { pitch: map.getPitch(), terrain: map.getTerrain(), source: map.getSource('mapterhorn-terrain') };
  })).toMatchObject({ pitch: 0, terrain: null, source: undefined });
  expect(demRequests).toBeGreaterThan(0);
});
