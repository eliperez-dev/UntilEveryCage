import { expect, test } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

test('live candidate map keeps the repaired controls and default V1 pins operable', async ({ page }, testInfo) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires the configured live preview.');
  test.setTimeout(120_000);

  await page.goto('/v2-preview/#/map?list=closed');
  await expect(page.locator('.lab')).toHaveAttribute('data-data-mode', 'candidate-preview');

  const mapStyle = page.getByLabel('Map style');
  await expect(mapStyle).toHaveValue('vector');
  await expect(mapStyle.locator('option')).toHaveText(['Street', 'Satellite']);
  await expect(page.getByRole('button', { name: 'Account unavailable' })).toHaveCount(0);
  await expect(page.locator('video')).toHaveCount(0);

  const pinTarget = await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    if (!map?.isStyleLoaded()) return null;
    for (const layer of ['v1-source-pins', 'mvt-v1-source-pins']) {
      if (!map.getLayer(layer) || map.getLayoutProperty(layer, 'visibility') !== 'visible') continue;
      const source = layer === 'mvt-v1-source-pins' ? 'preview-mvt' : 'locations';
      const options = layer === 'mvt-v1-source-pins' ? { sourceLayer: 'uec_preview' } : undefined;
      const feature = map.querySourceFeatures(source, options).find((item: any) =>
        item.properties?.kind === 'source-coordinate' || item.properties?.kind === 'source_coordinate');
      if (feature) return { layer, coordinates: feature.geometry.coordinates };
    }
    return null;
  }, undefined, { timeout: 60_000 });

  const { layer, coordinates } = await pinTarget.jsonValue<{ layer: string; coordinates: [number, number] }>();
  await page.screenshot({ path: testInfo.outputPath('map-list-closed.png') });
  await page.evaluate(({ center }) => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    map.jumpTo({ center, zoom: 14 });
  }, { center: coordinates });
  await page.waitForFunction((visibleLayer) => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.queryRenderedFeatures({ layers: [visibleLayer] }).length > 0;
  }, layer, { timeout: 30_000 });
  const pinPoint = await page.evaluate((visibleLayer) => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const feature = map.queryRenderedFeatures({ layers: [visibleLayer] })[0];
    const point = map.project(feature.geometry.coordinates);
    const bounds = map.getContainer().getBoundingClientRect();
    return { x: bounds.left + point.x, y: bounds.top + point.y };
  }, layer);
  await page.mouse.click(pinPoint.x, pinPoint.y);
  await expect(page.locator('.reading-sheet')).toBeVisible({ timeout: 30_000 });

  await page.getByRole('button', { name: 'Close record detail' }).click();
  await page.getByRole('button', { name: 'Search map' }).click();
  await expect(page.locator('.results-heading').last().locator('span')).toHaveText(/^\d+ matching · 100 shown$/);
  await page.locator('details.filters > summary').click();
  const source = page.getByRole('group', { name: 'Source' });
  await expect(source).toBeVisible({ timeout: 30_000 });
  await source.locator('input[type="checkbox"]').first().check();
  const search = page.getByRole('searchbox', { name: 'Search across preview records' });
  await search.fill('a');
  const clear = page.getByRole('button', { name: 'Clear all filters' });
  await expect(clear).toBeVisible();
  await clear.click();
  await expect(search).toHaveValue('');
  await expect(source.locator('input[type="checkbox"]').first()).not.toBeChecked();

  await page.getByRole('button', { name: 'Release' }).click();
  const release = page.getByLabel('Current release');
  await expect(release).toBeVisible();
  await expect(release.locator('option:disabled')).toHaveCount(0);
  const releaseMenu = page.getByRole('complementary', { name: 'Release details' });
  const [selectBox, menuBox] = await Promise.all([release.boundingBox(), releaseMenu.boundingBox()]);
  expect(selectBox).not.toBeNull();
  expect(menuBox).not.toBeNull();
  for (const box of [selectBox!, menuBox!]) {
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width);
    expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  }
  await expect(page.getByText('Connections', { exact: true })).toHaveCount(0);

  await page.goto('/v2-preview/#/about/help');
  await expect(page.getByRole('heading', { level: 1, name: 'Help' })).toBeVisible();
  await expect(page.locator('video')).toHaveCount(0);
});
