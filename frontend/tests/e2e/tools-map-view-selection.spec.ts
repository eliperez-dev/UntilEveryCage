import { expect, test } from '@playwright/test';

async function installMapTiles(page: import('@playwright/test').Page) {
  const images = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 256;
    const context = canvas.getContext('2d')!;
    context.fillStyle = '#252b28';
    context.fillRect(0, 0, 256, 256);
    return {
      png: canvas.toDataURL('image/png').split(',')[1],
      webp: canvas.toDataURL('image/webp').split(',')[1],
    };
  });
  const png = Buffer.from(images.png, 'base64');
  const webp = Buffer.from(images.webp, 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: png }));
  await page.route('**/World_Imagery/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: png }));
  await page.route('https://tiles.mapterhorn.com/**', route => route.fulfill({ status: 200, contentType: 'image/webp', body: webp }));
}

test('Tools map controls operate the active map without removing Search map', async ({ page }) => {
  await installMapTiles(page);
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4');
  const map = page.getByLabel('Map showing records');
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getLayer('exact-pins')))).toBe(true);
  await expect(page.getByRole('button', { name: 'Search map' })).toBeVisible();
  await expect(map.locator('.map-controls-wrap')).toHaveCount(0);

  await page.getByRole('button', { name: 'Tools' }).click();
  const controls = page.getByRole('group', { name: 'Map view' });
  const style = controls.getByLabel('Map style');
  const camera = controls.locator('.map-camera-toggle');
  await expect(style).toBeEnabled();
  await expect(camera).toHaveText('2D');
  await style.selectOption('satellite');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0])).toContain('World_Imagery');
  await camera.click();
  await expect(camera).toHaveText('3D');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(45);
  await expect(page.getByRole('button', { name: 'Search map' })).toBeVisible();
});

for (const listState of ['closed', 'open'] as const) {
  test(`map pin selection opens its detail and centers the camera with Search ${listState}`, async ({ page }) => {
    await page.goto(`./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4&list=${listState}`);
    await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getLayer('exact-pins')))).toBe(true);
    if (listState === 'open') await expect(page.locator('#field-record-list')).toBeVisible();
    else await expect(page.getByRole('button', { name: 'Search map' })).toBeVisible();

    const mapPoint = await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const feature = {
        type: 'Feature', geometry: { type: 'Point', coordinates: [-73.9, 40.7] },
        properties: { id: 'dense-exact-0-0' }, layer: { id: 'exact-pins' },
      };
      map.jumpTo({ center: [-73.9, 40.7], zoom: 8 });
      map.queryRenderedFeatures = (_point: unknown, options: { layers?: string[] } = {}) =>
        options.layers?.includes('exact-pins') ? [feature] : [];
      return map.getCanvas().getBoundingClientRect().toJSON();
    });
    await page.mouse.click(mapPoint.x + mapPoint.width * 0.65, mapPoint.y + mapPoint.height * 0.5);
    await expect(page.locator('.dossier')).toBeVisible();
    await expect(page.locator('.dossier')).toContainText('Synthetic');
    await expect.poll(() => page.evaluate(() => {
      const center = (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getCenter();
      return center ? [Number(center.lng.toFixed(1)), Number(center.lat.toFixed(1))] : null;
    })).toEqual([-73.9, 40.7]);
  });
}
