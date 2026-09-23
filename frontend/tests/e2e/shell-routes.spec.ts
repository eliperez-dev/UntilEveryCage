import { test, expect } from '@playwright/test';

const routeTail = (page: import('@playwright/test').Page, tail: string) =>
  expect(new URL(page.url()).pathname.endsWith(`/${tail}`)).toBeTruthy();

test('the shared shell exposes the primary map and database routes', async ({ page }) => {
  await page.goto('./map');
  await expect(page.getByRole('banner')).toBeVisible();
  await expect(page.getByRole('navigation')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: /map/i })).toBeVisible();
  await expect(page.getByRole('link', { name: /database/i })).toBeVisible();
  await page.getByRole('link', { name: /database/i }).click();
  await routeTail(page, 'database');
  await expect(page.getByRole('heading', { level: 1, name: /database/i })).toBeVisible();
  await expect(page.getByRole('link', { name: /map/i })).toBeVisible();
});

test('a record URL is directly addressable and has a route-specific heading', async ({ page }) => {
  await page.goto('./records/synthetic-record-1');
  await routeTail(page, 'records/synthetic-record-1');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('navigation')).toBeVisible();
  await expect(page.getByRole('link', { name: /database/i })).toBeVisible();
});

test('the shell keeps route context in the URL through back and forward navigation', async ({ page }) => {
  await page.goto('./map?profile=community&query=synthetic#view=world');
  await expect(page.getByRole('heading', { level: 1, name: /map/i })).toBeVisible();
  await page.getByRole('link', { name: /database/i }).click();
  await routeTail(page, 'database');
  await expect.poll(() => new URL(page.url()).searchParams.get('profile')).toBe('community');
  await expect.poll(() => new URL(page.url()).searchParams.get('query')).toBe('synthetic');
  await page.goBack();
  await routeTail(page, 'map');
  await expect.poll(() => new URL(page.url()).hash).toBe('#view=world');
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
  await page.goto('./not-a-public-route');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('link', { name: /map/i })).toBeVisible();
});

test('record loading and request failure are announced with accessible status roles', async ({ page }) => {
  let allowFailure: (() => void) | undefined;
  let sawRequest: (() => void) | undefined;
  const requestStarted = new Promise<void>(resolve => { sawRequest = resolve; });
  const heldResponse = new Promise<void>(resolve => { allowFailure = resolve; });
  await page.route('**/api/**', async route => {
    sawRequest?.();
    await heldResponse;
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Service unavailable' } }) });
  });
  await page.goto('./records/synthetic-record-1');
  await requestStarted;
  await expect(page.getByRole('status')).toBeVisible();
  allowFailure?.();
  await expect(page.getByRole('alert')).toBeVisible();
});

test('missing records use a generic unavailable state', async ({ page }) => {
  await page.route('**/api/**', route => route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Not available' } }) }));
  await page.goto('./records/synthetic-missing-record');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByText(/not available|not found/i)).toBeVisible();
});

test('route controls remain keyboard reachable', async ({ page }) => {
  await page.goto('./map');
  await expect(page.getByRole('main')).toBeVisible();
  const mainHeading = page.getByRole('heading', { level: 1 });
  await mainHeading.focus();
  await expect(mainHeading).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.locator(':focus')).toBeVisible();
});
