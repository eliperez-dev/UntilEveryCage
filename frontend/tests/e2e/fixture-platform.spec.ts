import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.beforeEach(async ({ page }) => {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const localApiAllowed = process.env.LOCAL_V2_E2E === '1' && url.origin === 'http://127.0.0.1:8000';
    if (url.origin !== 'http://127.0.0.1:4173' && !localApiAllowed) throw new Error(`Unexpected external request: ${url.href}`);
    await route.continue();
  });
});

test('renders the synthetic evidence desk', async ({ page }) => {
  await page.goto('./#/');
  await expect(page).toHaveTitle(/Until Every Cage/);
  await expect(page.getByRole('heading', { name: /See what a record can/i })).toBeVisible();
  await expect(page.getByText('SYNTHETIC PREVIEW')).toBeVisible();
});

test('moves through the accessible synthetic scale slice into the explorer', async ({ page }) => {
  await page.goto('./#/');
  await expect(page.getByRole('heading', { name: 'Start with one individual.' })).toBeVisible();
  await expect(page.getByText('MODEL ESTIMATE · SYNTHETIC')).toBeVisible();
  const scale = page.getByLabel('How large is the example?');
  await scale.press('ArrowRight');
  await expect(page.getByText('10')).toBeVisible();
  await expect(page.getByText(/fictional interaction, not a published facility/)).toBeVisible();
  await page.getByRole('link', { name: /Continue to the source-linked explorer/ }).click();
  await expect(page.getByRole('heading', { name: 'Choose the evidence lane' })).toBeVisible();
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
  await page.getByRole('link', { name: /UNTIL EVERY CAGE/ }).focus();
  await expect(page.locator(':focus')).toHaveAttribute('href', '/v2-preview/#/');
  await page.getByRole('link', { name: /Ethics & safeguards/ }).focus();
  await expect(page.locator(':focus')).toHaveAttribute('href', '/ethics.html');
  await page.getByLabel('Profile').focus();
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
  await page.goBack();
  await expect(page).toHaveURL(/#\//);
  await expect(page.getByRole('heading', { name: 'North Star Cooperative' })).toBeVisible();
});

test('shows the local map and limited export context', async ({ page }) => { await page.goto('./#/'); await page.getByRole('button', { name: 'Show map' }).click(); await expect(page.getByLabel('Synthetic location map')).toBeVisible(); await expect(page.getByText(/no external tiles/)).toBeVisible(); await page.getByRole('button', { name: 'Preview export' }).click(); const exportPanel=page.locator('.export-preview'); await expect(exportPanel.getByText('IN-MEMORY EXPORT PREVIEW')).toBeVisible(); await expect(exportPanel.locator('p').filter({hasText:'Loaded results only'})).toBeVisible(); });

test('local mode fails safely on a mocked 503 without fixture fallback', async ({ page }) => { await page.route('**/api/v2/locations*', (route) => route.fulfill({ status: 503, body: 'unavailable' })); await page.goto('./?mode=local-v2#/'); await expect(page.getByRole('alert')).toContainText('Could not load local V2 data'); await expect(page.getByText('Local V2 mode · no fixture fallback')).toBeVisible(); await expect(page.getByRole('button', { name: /North Star Cooperative/ })).toHaveCount(0); });
