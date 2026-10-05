import { expect, test } from '@playwright/test';

test('map shell mounts and keeps Search, map modes, and navigation operable', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');
  await page.goto('/#/map?f1a=field&list=closed');

  const search = page.getByRole('button', { name: /Search map Places, facilities, sources/ });
  await expect(search).toBeVisible(); // Regression: Field must not treat its `state` prop as a store.
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Map' })).toHaveAttribute('aria-current', 'page');
  await expect(page.locator('.maplibregl-ctrl-zoom-in')).toHaveCount(0);

  await search.click();
  await expect(search).toHaveCount(0); // The drawer replaces the button in place.
  await expect(page.getByRole('searchbox', { name: 'Search across preview records' })).toBeVisible();
  await page.getByRole('button', { name: 'Close search panel' }).click();
  await expect(search).toBeVisible();

  const mapLens = page.getByRole('complementary', { name: 'Map lens' });
  await mapLens.getByRole('button', { name: /Map lens/ }).click();
  const muted = mapLens.getByRole('button', { name: 'Muted' });
  await expect(muted).toBeVisible();
  await muted.click();
  await expect(muted).toHaveAttribute('aria-pressed', 'true');

  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database' }).click();
  await expect(page.getByRole('heading', { name: 'Research index' })).toBeVisible();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Map' }).click();
  await expect(search).toBeVisible();
});

test('the four primary links retain the rich preview context across Contribute and About', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires the isolated local preview fixture');
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  await page.route('https://server.arcgisonline.com/**', route => route.abort());
  await page.route('**/dev/real-preview/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith('/counts')
      ? { api_version: 'real-preview-v1', data: { facility_candidate_count: 0, numeric_coordinate_count: 0, city_postal_count: 0, map_visible_count: 0 } }
      : path.endsWith('/facets')
        ? { api_version: 'real-preview-v1', data: [] }
        : { api_version: 'real-preview-v1', data: [], meta: { private_preview: true, next_cursor: null } };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  const primary = page.getByRole('navigation', { name: 'Primary' });
  await page.goto('/#/map?f1a=field&list=closed');
  await expect(page.getByRole('button', { name: /Search map Places, facilities, sources/ })).toBeVisible();
  for (const label of ['Map', 'Database', 'Contribute', 'About']) await expect(primary.getByRole('link', { name: label })).toBeVisible();

  await primary.getByRole('link', { name: 'Contribute' }).click();
  await expect(page.getByRole('heading', { name: 'Contribute' })).toBeVisible();
  await expect.poll(() => new URL(page.url()).hash).toContain('map=%23%2Fmap%3Ff1a%3Dfield');
  const shellNav = page.getByRole('navigation', { name: 'Main navigation' });
  for (const label of ['Map', 'Database', 'Contribute', 'About']) await expect(shellNav.getByRole('link', { name: label })).toBeVisible();

  await shellNav.getByRole('link', { name: 'About' }).click();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage' })).toBeVisible();
  await shellNav.getByRole('link', { name: 'Map' }).click();
  await expect(page.getByRole('button', { name: /Search map Places, facilities, sources/ })).toBeVisible();
  for (const label of ['Map', 'Database', 'Contribute', 'About']) await expect(primary.getByRole('link', { name: label })).toBeVisible();

  await primary.getByRole('link', { name: 'Database' }).click();
  await expect(page.getByRole('heading', { name: 'Research index' })).toBeVisible();
  for (const label of ['Map', 'Database', 'Contribute', 'About']) await expect(primary.getByRole('link', { name: label })).toBeVisible();
  expect(new URL(page.url()).hash).toContain('f1a=field');
  await primary.getByRole('link', { name: 'Map' }).click();
  await expect(page.getByRole('button', { name: /Search map Places, facilities, sources/ })).toBeVisible();
  expect(new URL(page.url()).hash).toContain('f1a=field');
});

test('320px shell keeps the locator clear of counts and hides it behind Debug', async ({ page }) => {
  test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/#/map?f1a=field&list=closed');
  const locator = page.locator('.world-position');
  const counts = page.locator('.private-counts');
  await expect(locator).toBeVisible();
  await expect(counts).toBeVisible();
  const locatorBox = await locator.boundingBox();
  const countsBox = await counts.boundingBox();
  expect(locatorBox && countsBox && locatorBox.y + locatorBox.height < countsBox.y).toBe(true);

  await page.getByRole('button', { name: 'Debug menu' }).click();
  await expect(page.getByRole('complementary', { name: 'Debug menu' })).toBeVisible();
  await expect(locator).toBeHidden();
});
