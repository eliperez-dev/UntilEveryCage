import { test, expect } from '@playwright/test';

test('fresh Belgium city aggregate is visible on the real map and opens selectable detail', async ({ page }) => {
  test.setTimeout(120_000);
  const requested: string[] = [];
  page.on('request', request => {
    const url = new URL(request.url());
    requested.push(url.pathname + url.search);
  });
  await page.goto('/#/map?f1a=field&lat=50.7&lon=4.6&z=8&list=closed');
  const countsResponse = await page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/counts') && response.status() === 200);
  const counts = await countsResponse.json();
  expect(counts.data.facility_candidate_count).toBeGreaterThan(0);
  expect(counts.data.map_visible_count).toBeGreaterThan(0);
  expect(counts.data.map_visible_count).toBeLessThanOrEqual(counts.data.facility_candidate_count);
  const latestRun = counts.meta.runtime_ledger.find((entry: { source_id?: string }) => entry.source_id === 'be.locations');
  expect(latestRun?.run_id).toMatch(/^preview-be-locations-[0-9a-f-]{36}$/i);

  const viewportResponse = await page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/viewport') && response.status() === 200);
  const viewport = await viewportResponse.json();
  expect(viewport.data.length).toBeGreaterThan(0);
  expect(viewport.data[0].display_precision).toBe('city_reference_approximate');
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await expect(page.getByText('Loading map records…')).toHaveCount(0, { timeout: 60_000 });
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.querySourceFeatures('locations').some((feature: any) => feature.properties.kind === 'aggregate' && feature.properties.precision === 'city');
  }, undefined, { timeout: 60_000 });
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.queryRenderedFeatures({ layers: ['aggregate-outer', 'cluster-outer'] }).length ?? 0), { timeout: 10_000 }).toBeGreaterThan(0);
  const aggregateMembers = page.locator('#field-record-list ol li button');
  await page.getByRole('button', { name: /Open approximate city location/ }).first().click();
  await expect(aggregateMembers.first()).toBeVisible();
  const memberNames = await aggregateMembers.allInnerTexts();
  expect(memberNames.length).toBeGreaterThan(0);
  expect(memberNames.every(name => name.includes('Approximate city location · not a facility point'))).toBe(true);
  await aggregateMembers.first().click();
  await expect(page.getByRole('heading', { level: 2 })).toBeVisible();
  await expect(page.locator('.reading-sheet').getByText('Approximate city location · not a facility point')).toBeVisible();
  await expect(page.locator('.reading-sheet').getByText(/Approximate city location — not a facility point; private preview only/)).toBeVisible();
  expect(requested.some(path => path.includes('/locations/'))).toBe(true);
  expect(requested.some(path => path.includes('token') || path.includes('secret'))).toBe(false);
  const storage = await page.evaluate(() => JSON.stringify({ localStorage, sessionStorage }));
  expect(storage).not.toMatch(/uec-dev-preview-token|postgresql:|preview-[a-z0-9-]{20,}/i);
});
