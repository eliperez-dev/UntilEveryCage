import { expect, test } from '@playwright/test';

// This suite needs the populated, same-origin private preview. Fixture-only
// runs still exercise the structural shell in shell-routes.spec.ts.
test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');

test('database selection opens a stable record URL and returns to the map', async ({ page }) => {
  await page.goto('./#/database');
  const firstRecord = page.locator('.records button').first();
  await expect(firstRecord).toBeVisible();
  await firstRecord.click();

  const fullRecord = page.getByRole('link', { name: /Open full record/ });
  await expect(fullRecord).toHaveAttribute('href', /#\/records\/[0-9a-f-]{36}$/i);
  await fullRecord.click();
  await expect.poll(() => new URL(page.url()).hash).toMatch(/^#\/records\/[0-9a-f-]{36}$/i);
  await expect(page.getByRole('article')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Location' })).toBeVisible();

  await page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('link', { name: 'Map' }).click();
  await expect(page.getByRole('region', { name: 'Map showing records' })).toBeVisible();
});

test('map selection can open the same full record without losing the route', async ({ page }) => {
  await page.goto('./#/map?f1a=field');
  const firstRecord = page.locator('.record-list button').first();
  await expect(firstRecord).toBeVisible();
  await firstRecord.click();
  const fullRecord = page.getByRole('link', { name: 'Open full record' });
  await expect(fullRecord).toBeVisible();
  await fullRecord.click();
  await expect.poll(() => new URL(page.url()).hash).toMatch(/^#\/records\/[0-9a-f-]{36}$/i);
  await expect(page.getByRole('article')).toBeVisible();
});
