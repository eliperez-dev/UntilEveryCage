import { expect, test } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

test('configured candidate database opens source-native detail facts', async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto('/v2-preview/#/database?f1a=field&source=us.fsis');
  const table = page.getByRole('table', { name: 'Browse records' });
  await expect(table).toBeVisible({ timeout: 60_000 });
  await table.getByRole('button').first().click();

  const detail = page.locator('.selection');
  await expect(detail.getByRole('heading', { name: 'Source facts' })).toBeVisible({ timeout: 30_000 });
  await expect(detail.getByText('Location precision', { exact: true })).toBeVisible();
  await expect(detail.getByText('Also known as', { exact: true })).toBeVisible();
  await expect(detail.getByText('Processing activities', { exact: true })).toBeVisible();
  await expect(detail.getByText('Source volume categories', { exact: true })).toBeVisible();
  await expect(detail).not.toContainText('API unavailable');
  await expect(detail).not.toContainText('Name not shown, privacy review pending');
});

test('candidate map exposes projection-cache invalidation through Tools', async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto('/v2-preview/#/map?f1a=field&source=us.fsis');
  await page.getByRole('button', { name: 'Tools' }).click();
  await page.getByLabel('Enable debug menu').check();
  await page.getByRole('button', { name: 'Debug menu' }).click();
  const debug = page.getByRole('complementary', { name: 'Debug menu' });
  await expect(debug.getByRole('button', { name: 'Clear map projection cache' })).toBeVisible({ timeout: 60_000 });
  await debug.getByRole('button', { name: 'Clear map projection cache' }).click();
  await expect(debug.locator('small[role="status"]')).toContainText(/cache/i);
});

test('candidate map marker opens the configured source-backed detail', async ({ page }) => {
  test.setTimeout(90_000);
  const feedTiming: { requested?: number; response?: number; finished?: number; status?: number } = {};
  page.on('request', request => { if (new URL(request.url()).pathname.endsWith('/api/dev/preview/test-release/map/feed')) feedTiming.requested = Date.now(); });
  page.on('response', response => { if (new URL(response.url()).pathname.endsWith('/api/dev/preview/test-release/map/feed')) { feedTiming.response = Date.now(); feedTiming.status = response.status(); } });
  page.on('requestfinished', request => { if (new URL(request.url()).pathname.endsWith('/api/dev/preview/test-release/map/feed')) feedTiming.finished = Date.now(); });
  await page.goto('/v2-preview/#/map?f1a=field&source=us.fsis');
  try {
    await page.waitForFunction(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return Boolean(map?.isStyleLoaded() && map.getSource('locations') && map.querySourceFeatures('locations').some((feature: any) => feature.properties?.kind === 'source-coordinate'));
    }, undefined, { timeout: 60_000 });
  } catch {
    const state = await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return {
        styleLoaded: Boolean(map?.isStyleLoaded()),
        sourcePresent: Boolean(map?.getSource('locations')),
        sourceFeatures: map?.getSource('locations') ? map.querySourceFeatures('locations').length : 0,
        rendered: map?.queryRenderedFeatures({ layers: ['source-coordinate-points'] }).length ?? 0,
        status: document.querySelector('[role="status"]')?.textContent?.trim().slice(0, 80) ?? '',
      };
    });
    throw new Error(`candidate map marker probe stalled: ${JSON.stringify({ feedTiming, state })}`);
  }
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const sourceFeature = map.querySourceFeatures('locations').find((feature: any) => feature.properties?.kind === 'source-coordinate');
    map.jumpTo({ center: sourceFeature.geometry.coordinates, zoom: 14 });
  });
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.queryRenderedFeatures({ layers: ['source-coordinate-points'] }).length > 0;
  }, undefined, { timeout: 30_000 });
  const point = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const rendered = map.queryRenderedFeatures({ layers: ['source-coordinate-points'] })[0];
    const projected = map.project(rendered.geometry.coordinates);
    const bounds = map.getContainer().getBoundingClientRect();
    return { x: bounds.left + projected.x, y: bounds.top + projected.y };
  });
  await page.mouse.click(point.x, point.y);

  const detail = page.locator('.reading-sheet');
  await expect(detail.getByRole('heading', { name: 'Source facts' })).toBeVisible({ timeout: 30_000 });
  await expect(detail.getByText('Location precision', { exact: true })).toBeVisible();
});

test('candidate map retains native overlays and V1 selection across route and basemap changes', async ({ page }) => {
  test.setTimeout(90_000);
  const ready = () => page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return Boolean(map?.isStyleLoaded() && map.isSourceLoaded('locations') && ['clusters', 'aggregate-outer', 'source-coordinate-points', 'v1-source-pins'].every(id => map.getLayer(id)));
  }, undefined, { timeout: 60_000 });
  await page.goto('/v2-preview/#/map?f1a=field&source=us.fsis');
  await ready();
  const first = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return {
      sourceCount: map.querySourceFeatures('locations').length,
      referencePaint: map.getPaintProperty('aggregate-outer', 'circle-stroke-color'),
      coordinateColor: map.getPaintProperty('source-coordinate-points', 'circle-color'),
    };
  });
  expect(first.sourceCount).toBeGreaterThan(0);
  expect(first.referencePaint).toBe('#e06b5b');
  expect(first.coordinateColor).toBeTruthy();

  await page.getByRole('button', { name: 'Tools' }).click();
  await page.getByLabel('Enable debug menu').check();
  await page.getByRole('button', { name: 'Debug menu' }).click();
  await page.getByLabel('Use V1 facility pin PNG + shadow').check();
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getLayoutProperty('v1-source-pins', 'visibility') === 'visible');
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const sourceFeature = map.querySourceFeatures('locations').find((feature: any) => feature.properties?.kind === 'source-coordinate');
    map.jumpTo({ center: sourceFeature.geometry.coordinates, zoom: 14 });
  });
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.queryRenderedFeatures({ layers: ['v1-source-pins'] }).length > 0, undefined, { timeout: 30_000 });
  const point = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const feature = map.queryRenderedFeatures({ layers: ['v1-source-pins'] })[0];
    const coordinate = map.project(feature.geometry.coordinates);
    const bounds = map.getContainer().getBoundingClientRect();
    return { x: bounds.left + coordinate.x, y: bounds.top + coordinate.y };
  });
  await page.mouse.click(point.x, point.y);
  await expect(page.locator('.reading-sheet').getByRole('heading', { name: 'Source facts' })).toBeVisible({ timeout: 30_000 });

  await page.goto('/v2-preview/#/database?f1a=field&source=us.fsis');
  await page.goto('/v2-preview/#/map?f1a=field&source=us.fsis');
  await ready();
  await page.getByLabel('Map style').selectOption('muted');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getPaintProperty('base', 'raster-saturation') === -1 && map.isSourceLoaded('locations') && ['clusters', 'aggregate-outer', 'source-coordinate-points', 'v1-source-pins'].every(id => map.getLayer(id));
  }, undefined, { timeout: 30_000 });
  await page.getByLabel('Map style').selectOption('vector');
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPaintProperty('base', 'raster-saturation') === 0);
  await page.getByLabel('Map style').selectOption('satellite');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isSourceLoaded('locations') && ['clusters', 'aggregate-outer', 'source-coordinate-points', 'v1-source-pins'].every(id => map.getLayer(id));
  }, undefined, { timeout: 30_000 });
});
