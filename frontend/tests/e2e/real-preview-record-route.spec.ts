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
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('./#/map?f1a=field');
  const firstRecord = page.locator('.record-list button').first();
  await expect(firstRecord).toBeVisible({ timeout: 20_000 });
  await firstRecord.click();
  const fullRecord = page.getByRole('link', { name: 'Open full record' });
  await expect(fullRecord).toBeVisible();
  await fullRecord.click();
  await expect.poll(() => new URL(page.url()).hash).toMatch(/^#\/records\/[0-9a-f-]{36}$/i);
  await expect(page.getByRole('article')).toBeVisible();
});

test('map dossier closes with Escape, Back, and its visible close button, restoring list focus', async ({ page }) => {
  await page.goto('./#/map?f1a=field');
  const firstRecord = page.locator('.record-list button').first();
  await expect(firstRecord).toBeVisible({ timeout: 20_000 });
  await firstRecord.click();
  await expect(page.getByRole('button', { name: 'Close record detail' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Close record detail' })).toHaveCount(0);
  await expect(firstRecord).toBeFocused();

  await firstRecord.click();
  await page.goBack();
  await expect(page.getByRole('button', { name: 'Close record detail' })).toHaveCount(0);
  await page.goForward();
  await expect(page.getByRole('button', { name: 'Close record detail' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Close record detail' })).toBeFocused();
  await page.getByRole('button', { name: 'Close record detail' }).click();
  await expect(page.getByRole('button', { name: 'Close record detail' })).toHaveCount(0);
  await expect(firstRecord).toBeFocused();
});

for (const width of [375, 768]) test(`${width}px dossier can be dismissed and its candidate opens a stable full record`, async ({ page }) => {
  await page.setViewportSize({ width, height: 844 });
  await page.goto('./#/map?f1a=field');
  const firstRecord = page.locator('.record-list button').first();
  await expect(firstRecord).toBeVisible({ timeout: 20_000 });
  await firstRecord.click();
  await expect(page.getByRole('button', { name: 'Close record detail' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Open full record/ })).toBeVisible();
  await page.getByRole('button', { name: 'Close record detail' }).click();
  await expect(page.getByRole('button', { name: 'Close record detail' })).toHaveCount(0);
  await expect(firstRecord).toBeFocused();
  await firstRecord.click();
  await page.getByRole('link', { name: /Open full record/ }).click();
  await expect.poll(() => new URL(page.url()).hash).toMatch(/^#\/records\/[0-9a-f-]{36}$/i);
  await expect(page.getByRole('article')).toBeVisible();
  await expect(page.getByText('Name not shown — privacy review pending')).toBeVisible();
});

test('fixture scenario flags cannot replace the populated real map', async ({ page }) => {
  await page.goto('./#/map?f1a=field&scenario=empty');
  await expect(page.getByRole('region', { name: 'Map showing records' })).toBeVisible();
  await expect(page.getByText('No records match this search and these filters.')).toHaveCount(0);
});
