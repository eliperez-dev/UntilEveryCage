import { test, expect } from '@playwright/test';

function isApiEndpoint(url: string): boolean {
  const pathname = new URL(url).pathname.replace(/^\/v2-preview(?=\/)/, '');
  return pathname.startsWith('/api/') || pathname.startsWith('/dev/real-preview/');
}

test('public routes stay local and never render fixture or API records', async ({ page }) => {
  const apiRequests: string[] = [];
  page.on('request', request => {
    if (isApiEndpoint(request.url())) apiRequests.push(request.url());
  });

  for (const route of ['#/map', '#/database', '#/records/synthetic-record-1', '#/locations/synthetic-record-1']) {
    await page.goto(`./${route}`);
    await expect(page.getByRole('banner')).toBeVisible();
    await expect(page.getByRole('main')).toBeVisible();
    await expect(page.getByText(/fixture record|private candidate|synthetic source/i)).toHaveCount(0);
    await expect(page.locator('[data-facility-id]')).toHaveCount(0);
  }

  expect(apiRequests).toEqual([]);
});

test('profile, search, and export inputs cannot reach an API from the shell', async ({ page }) => {
  const apiRequests: string[] = [];
  page.on('request', request => {
    if (isApiEndpoint(request.url())) apiRequests.push(request.url());
  });

  await page.goto('./?mode=local-v2#/map?profile=community&query=private%20address');
  await expect(page.getByRole('heading', { name: 'Map' })).toBeVisible();
  await expect(page.getByLabel(/profile|search/i)).toHaveCount(0);
  await expect(page.getByRole('button', { name: /download|export/i })).toHaveCount(0);
  expect(apiRequests).toEqual([]);
});

test('a route change cannot display a stale API response because no request is made', async ({ page }) => {
  let interceptedApiRequests = 0;
  await page.route(url => isApiEndpoint(url.href), async route => {
    interceptedApiRequests += 1;
    await route.fulfill({ status: 503, body: 'unavailable' });
  });

  await page.goto('./#/records/first-synthetic-record');
  await expect(page.getByRole('heading', { name: 'Record' })).toBeVisible();
  await page.goto('./#/records/second-synthetic-record');
  await expect(page.getByText('Record ID: second-synthetic-record')).toBeVisible();
  expect(interceptedApiRequests).toBe(0);
  await expect(page.getByText('Record ID: first-synthetic-record')).toHaveCount(0);
});
