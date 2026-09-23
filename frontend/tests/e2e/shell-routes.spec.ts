import { test, expect } from '@playwright/test';

const routeTail = (page: import('@playwright/test').Page, tail: string) =>
  expect(new URL(page.url()).hash).toBe(`#/${tail}`);

test('the shared shell exposes the primary map and database routes', async ({ page }) => {
  await page.goto('./#/map');
  await expect(page.getByRole('banner')).toBeVisible();
  await expect(page.getByRole('navigation')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: /map/i })).toBeVisible();
  await expect(page.getByRole('navigation').getByRole('link', { name: 'Database' })).toBeVisible();
  await page.getByRole('navigation').getByRole('link', { name: 'Database' }).click();
  await routeTail(page, 'database');
  await expect(page.getByRole('heading', { level: 1, name: /database/i })).toBeVisible();
  await expect(page.getByRole('navigation').getByRole('link', { name: 'Map' })).toBeVisible();
});

test('a record URL is directly addressable and has a route-specific heading', async ({ page }) => {
  await page.goto('./#/records/synthetic-record-1');
  await expect(new URL(page.url()).hash).toBe('#/records/synthetic-record-1');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('navigation')).toBeVisible();
  await expect(page.getByRole('navigation').getByRole('link', { name: 'Database' })).toBeVisible();
});

test('the shell keeps route context in the URL through back and forward navigation', async ({ page }) => {
  await page.goto('./#/map?profile=community&query=synthetic');
  await expect(page.getByRole('heading', { level: 1, name: /map/i })).toBeVisible();
  await page.getByRole('navigation').getByRole('link', { name: 'Database' }).click();
  await routeTail(page, 'database');
  await expect.poll(() => new URL(page.url()).hash).toBe('#/database');
  await page.goBack();
  await expect.poll(() => new URL(page.url()).hash).toBe('#/map?profile=community&query=synthetic');
  await page.goForward();
  await routeTail(page, 'database');
});

test('a hash route remains a supported entry point for the same shell destinations', async ({ page }) => {
  await page.goto('./#/map');
  await expect(page.getByRole('heading', { level: 1, name: /map/i })).toBeVisible();
  await page.goto('./#/database');
  await expect(page.getByRole('heading', { level: 1, name: /database/i })).toBeVisible();
});

test('an unknown path exposes an accessible not-found state and a route back to the map', async ({ page }) => {
  await page.goto('./#/not-a-public-route');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Return to the map' })).toBeVisible();
});

test('route controls are focusable links with explicit destinations', async ({ page }) => {
  await page.goto('./#/map');
  await expect(page.getByRole('main')).toBeVisible();
  const mapLink = page.getByRole('navigation').getByRole('link', { name: 'Map' });
  await mapLink.focus();
  await expect(mapLink).toBeFocused();
  await expect(mapLink).toHaveAttribute('href', '#/map');
  const databaseLink = page.getByRole('navigation').getByRole('link', { name: 'Database' });
  await databaseLink.focus();
  await expect(databaseLink).toBeFocused();
  await expect(databaseLink).toHaveAttribute('href', '#/database');
});
