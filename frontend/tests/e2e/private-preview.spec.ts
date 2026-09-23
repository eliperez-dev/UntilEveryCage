import { test, expect } from '@playwright/test';

test('private preview query does not expose operator controls or candidate data', async ({ page }) => {
  const previewRequests: string[] = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.includes('/api/dev/preview/')) previewRequests.push(request.url());
  });

  await page.goto('./?preview=dev-candidates&mode=local-v2#/map');
  await expect(page.getByRole('heading', { name: 'Map' })).toBeVisible();
  await expect(page.getByLabel(/operator token/i)).toHaveCount(0);
  await expect(page.getByRole('button', { name: /load private candidates|preview export/i })).toHaveCount(0);
  await expect(page.getByText(/private candidate|not reviewed or published/i)).toHaveCount(0);
  expect(previewRequests).toEqual([]);
});

test('failed preview responses cannot fall back to fixture records in the public shell', async ({ page }) => {
  let interceptedPreviewRequests = 0;
  await page.route('**/api/dev/preview/**', async route => {
    interceptedPreviewRequests += 1;
    await route.fulfill({ status: 401, body: JSON.stringify({ error: 'dev_preview_auth_failed' }) });
  });

  await page.goto('./?preview=dev-candidates#/records/synthetic-record-1');
  await expect(page.getByRole('heading', { name: 'Record' })).toBeVisible();
  await expect(page.getByText(/synthetic demonstration|private candidate facility/i)).toHaveCount(0);
  expect(interceptedPreviewRequests).toBe(0);
});

test('test-release mode cannot enable preview CSV or list/detail requests', async ({ page }) => {
  const previewRequests: string[] = [];
  page.on('request', request => {
    if (new URL(request.url()).pathname.includes('/api/dev/preview/')) previewRequests.push(request.url());
  });

  await page.goto('./?preview=test-release#/database');
  await expect(page.getByRole('heading', { name: 'Database' })).toBeVisible();
  await expect(page.getByRole('button', { name: /download|export/i })).toHaveCount(0);
  await expect(page.getByLabel(/operator token/i)).toHaveCount(0);
  expect(previewRequests).toEqual([]);
});
