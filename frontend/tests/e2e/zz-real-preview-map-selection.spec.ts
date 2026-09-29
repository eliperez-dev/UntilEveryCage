import { test, expect } from '@playwright/test';

test('real-preview map uses one weighted native-cluster feed and does not refetch on camera movement', async ({ page }) => {
  test.setTimeout(120_000);
  const requested: string[] = [];
  page.on('request', request => {
    const url = new URL(request.url());
    requested.push(url.pathname + url.search);
  });
  const feedPending = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/map/feed') && response.status() === 200);
  await page.goto('/#/map?f1a=field&lat=50.7&lon=4.6&z=8&list=closed');
  const countsResponse = await page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/counts') && response.status() === 200);
  const counts = await countsResponse.json();
  expect(counts.data.facility_candidate_count).toBeGreaterThan(0);
  expect(counts.data.map_visible_count).toBeGreaterThan(0);
  expect(counts.data.map_visible_count).toBeLessThanOrEqual(counts.data.facility_candidate_count);
  const latestRun = counts.meta.runtime_ledger.find((entry: { source_id?: string }) => entry.source_id === 'be.locations');
  expect(latestRun?.run_id).toMatch(/^preview-be-locations-[0-9a-f-]{36}$/i);

  const feedResponse = await feedPending;
  const feed = await feedResponse.json();
  expect(feed.meta).toMatchObject({ bounded: true, private_preview: true, scope: 'default_map_scope', zoom_max: 14 });
  expect(feed.data.length).toBeGreaterThan(0);
  expect(feed.data.every((feature: any) => ['source_coordinate', 'city_reference'].includes(feature.kind))).toBe(true);
  expect(feed.data.every((feature: any) => Number.isSafeInteger(feature.weight) && feature.weight > 0)).toBe(true);
  expect(feed.data.reduce((total: number, feature: any) => total + feature.weight, 0)).toBe(feed.meta.total_weight);
  expect(feed.data[0]).not.toHaveProperty('address');
  expect(feed.data[0]).not.toHaveProperty('name');
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await expect(page.getByText('Loading map records…')).toHaveCount(0, { timeout: 60_000 });
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const source = map?.getSource('locations');
    return map?.isStyleLoaded() && source && map.getLayer('clusters') && map.getLayer('aggregate-outer') && map.getLayer('source-coordinate-points');
  }, undefined, { timeout: 60_000 });
  const firstFeedCount = requested.filter(path => path.includes('/map/feed')).length;
  expect(firstFeedCount).toBe(1);
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    map.easeTo({ center: [8, 54], zoom: 5, duration: 0 });
  });
  await page.waitForTimeout(250);
  expect(requested.filter(path => path.includes('/map/feed')).length).toBe(firstFeedCount);
  expect(requested.some(path => path.endsWith('/viewport'))).toBe(false);
  expect(requested.some(path => path.includes('/locations/'))).toBe(false);
  expect(requested.some(path => path.includes('token') || path.includes('secret'))).toBe(false);
  const storage = await page.evaluate(() => JSON.stringify({ localStorage, sessionStorage }));
  expect(storage).not.toMatch(/uec-dev-preview-token|postgresql:|preview-[a-z0-9-]{20,}/i);
});
