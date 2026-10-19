import { expect, test } from '@playwright/test';

test('production bundle opens a real v0 pin on cold and warm loads', async ({ page }, testInfo) => {
  test.skip(!process.env.UEC_PUBLIC_V0_PARITY, 'Requires an explicitly configured production build and real approved v0 API.');
  test.setTimeout(180_000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.name));
  const manifestResponse = await page.request.get('/api/v2/releases/manifest?profile=official');
  expect(manifestResponse.ok()).toBeTruthy();
  const identity = (await manifestResponse.json()).data;
  const params = new URLSearchParams({ profile: 'official', release_id: identity.release_id, format: 'compact' });
  const feedResponse = await page.request.get(`/api/v2/map/feed?${params}`);
  expect(feedResponse.ok()).toBeTruthy();
  const feed = await feedResponse.json();
  expect(feed.meta.dataset_version).toBe('v0');
  expect(feed.meta.public_record_count).toBe(63_601);
  // Select a real source-coordinate point entirely in memory, never a saved fixture.
  const point = feed.data.features.find((row: unknown[]) =>
    feed.data.dictionaries.precisions[row[6] as number] === 'source_reported'
    && feed.data.dictionaries.category_keys[row[4] as number] === 'slaughter');
  expect(Boolean(point)).toBeTruthy();
  const mapPath = `/#/map?lat=${point[2]}&lon=${point[1]}&z=16&list=closed`;

  async function readyAndOpenPin() {
    await expect(page.locator('.map-host canvas')).toBeVisible({ timeout: 60_000 });
    await expect(page.locator('.startup-status')).toHaveCount(0, { timeout: 60_000 });
    const mapBox = await page.locator('.map-host').boundingBox();
    expect(mapBox).not.toBeNull();
    await page.mouse.click(mapBox!.x + mapBox!.width / 2, mapBox!.y + mapBox!.height / 2 - 10);
    await expect(page.locator('.reading-sheet[aria-label="Record evidence"]')).toBeVisible({ timeout: 30_000 });
    await page.getByRole('button', { name: 'Close record detail' }).click();
  }

  await page.goto(mapPath);
  await readyAndOpenPin();
  await expect(page.locator('.reading-sheet')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('public-v0-map-closed.png') });
  await page.getByRole('button', { name: 'Release', exact: true }).click();
  const releaseDetails = page.getByRole('complementary', { name: 'Release details' });
  await expect(releaseDetails).toContainText('Early Access');
  await expect(releaseDetails).not.toContainText('v0-candidate-');
  await page.getByRole('button', { name: 'Release', exact: true }).click();

  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database', exact: true }).click();
  await expect(page.locator('#main-content')).toBeVisible();
  await expect(page.getByText(/Results are eligible public facility projection rows/)).toHaveCount(0);
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Contribute', exact: true }).click();
  await expect(page.getByText('Contribution forms aren’t available here', { exact: true })).toHaveCount(0);
  await expect(page.locator('a[href="mailto:untileverycageproject@protonmail.com"]').first()).toBeVisible();
  await expect(page.locator('form button[type="submit"]')).toHaveCount(0);

  await page.goto(mapPath);
  await page.reload();
  await readyAndOpenPin();
  const cachedPublicProjection = await page.evaluate(async () =>
    (await caches.keys()).some(name => name.startsWith('uec-public-map-projection-')));
  expect(cachedPublicProjection).toBeTruthy();
  expect(errors).toEqual([]);
});
