import { test, expect } from '@playwright/test';

test('real-preview map uses bounded cached MVT tiles without fetching the JSON feed', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');
  test.setTimeout(120_000);
  const requested: string[] = [];
  page.on('request', request => {
    const url = new URL(request.url());
    requested.push(url.pathname + url.search);
  });
  const countsPending = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/counts') && response.status() === 200);
  const tilePending = page.waitForResponse(response => /\/dev\/real-preview\/map\/tiles\/\d+\/\d+\/\d+/.test(new URL(response.url()).pathname) && response.status() === 200);
  await page.goto('/#/map?f1a=field&lat=50.7&lon=4.6&z=8&list=closed');
  const countsResponse = await countsPending;
  const counts = await countsResponse.json();
  expect(counts.data.facility_candidate_count).toBeGreaterThan(0);
  expect(counts.data.map_visible_count).toBeGreaterThan(0);
  expect(counts.data.map_visible_count).toBeLessThanOrEqual(counts.data.facility_candidate_count);
  const latestRun = counts.meta.runtime_ledger.find((entry: { source_id?: string }) => entry.source_id === 'be.locations');
  expect(latestRun?.run_id).toMatch(/^preview-be-locations-[0-9a-f-]{36}$/i);
  const tileResponse = await tilePending;
  expect(tileResponse.headers()['content-type']).toContain('application/vnd.mapbox-vector-tile');
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await expect(page.getByText(/Fetching map projection|Building cluster index|Drawing map marks/)).toHaveCount(0, { timeout: 60_000 });
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getSource('preview-mvt') && map.getLayer('mvt-clusters') && map.getLayer('mvt-reference-outer') && map.getLayer('mvt-source-coordinates');
  }, undefined, { timeout: 60_000 });
  expect(requested.some(path => path.includes('/map/tiles/'))).toBe(true);
  expect(requested.some(path => path.includes('/map/feed'))).toBe(false);
  await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    map.easeTo({ center: [8, 54], zoom: 5, duration: 0 });
    await new Promise<void>(resolve => map.once('idle', resolve));
  });
  expect(requested.some(path => path.endsWith('/viewport'))).toBe(false);
  expect(requested.some(path => path.includes('/locations/'))).toBe(false);
  expect(requested.some(path => path.includes('token') || path.includes('secret'))).toBe(false);
  const storage = await page.evaluate(() => JSON.stringify({ localStorage, sessionStorage }));
  expect(storage).not.toMatch(/uec-dev-preview-token|postgresql:|preview-[a-z0-9-]{20,}/i);
});
