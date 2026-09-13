import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.beforeEach(async ({ page }) => {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:4173') throw new Error(`Unexpected external request: ${url.href}`);
    await route.continue();
  });
});

test('renders the synthetic evidence desk', async ({ page }) => {
  await page.goto('./#/');
  await expect(page).toHaveTitle(/Until Every Cage/);
  await expect(page.getByRole('heading', { name: /See what a record can/i })).toBeVisible();
  await expect(page.getByText('SYNTHETIC PREVIEW')).toBeVisible();
});

test('selecting the community profile shows persistent warning context', async ({ page }) => {
  await page.goto('./#/');
  await page.getByLabel('Profile').selectOption('community');
  await expect(page.getByRole('note')).toContainText('Unreviewed community claim');
  await expect(page.getByRole('note')).toContainText('Not verified by Until Every Cage');
  await expect(page.getByText('VISIBLE RECORDS')).toBeVisible();
});

test('opens a direct hash detail route with a record context', async ({ page }) => {
  await page.goto('./#/locations/syn-river-meadow?profile=curated');
  await expect(page.getByRole('heading', { name: 'River Meadow Foods' })).toBeVisible();
  await expect(page.getByText('RECORD / syn-river-meadow')).toBeVisible();
});

test('controls are keyboard reachable with visible focus', async ({ page }) => {
  await page.goto('./#/');
  await page.keyboard.press('Tab');
  await expect(page.locator(':focus')).toHaveAttribute('href', '/v2-preview/#/');
  await page.keyboard.press('Tab');
  await expect(page.locator(':focus')).toHaveAttribute('href', '/ethics.html');
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Profile')).toBeFocused();
  await page.keyboard.press('End');
  await expect(page.locator(':focus')).toBeVisible();
});

test('has no obvious accessibility violations at mobile width', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./#/');
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
  await expect(page.getByRole('heading', { name: /See what a record can/i })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(() => document.documentElement.clientWidth));
});

test('filters the curated list and updates the detail hash on selection', async ({ page }) => {
  await page.goto('./#/');
  await page.getByLabel('Search locations').fill('dairy');
  await expect(page.getByRole('button', { name: /River Meadow Foods/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /North Star Cooperative/ })).toHaveCount(0);
  await page.getByRole('button', { name: /River Meadow Foods/ }).click();
  await expect(page).toHaveURL(/#\/locations\/syn-river-meadow\?profile=curated/);
  await expect(page.getByRole('heading', { name: 'River Meadow Foods' })).toBeVisible();
});
