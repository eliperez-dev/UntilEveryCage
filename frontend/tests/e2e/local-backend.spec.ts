import { test, expect } from '@playwright/test';

test.skip(process.env.LOCAL_V2_E2E !== '1', 'Set LOCAL_V2_E2E=1 to run against the real local backend');

test('renders the real seeded local V2 record and opens its detail route', async ({ page }) => {
  const apiUrl = process.env.UEC_E2E_API_URL ?? process.env.LOCAL_V2_API_URL ?? 'http://127.0.0.1:8000';
  let list: { data?: Array<{ facility_id: string; canonical_name: string }> } = {};
  const response = await fetch(`${apiUrl}/api/v2/locations?profile=official&limit=1`);
  expect(response.ok).toBeTruthy();
  list = await response.json() as typeof list;
  const record = list.data?.[0];
  // The disposable candidate fixture must remain absent from public V2.
  if (!record) { expect(list.data).toEqual([]); return; }
  expect(record?.facility_id).toBeTruthy();
  expect(record?.canonical_name).toBeTruthy();
  await page.route('**/api/v2/**', async route => {
    const requestUrl = new URL(route.request().url());
    const upstream = await fetch(`${apiUrl}${requestUrl.pathname}${requestUrl.search}`);
    await route.fulfill({ status: upstream.status, headers: { 'content-type': upstream.headers.get('content-type') ?? 'application/json' }, body: await upstream.text() });
  });
  await page.goto('./?mode=local-v2#/');
  const resultButton = page.getByRole('button', { name: new RegExp(record?.canonical_name ?? '') });
  await expect(resultButton).toBeVisible();
  await resultButton.click();
  await expect(page.getByRole('heading', { name: record?.canonical_name ?? '' })).toBeVisible();
  await expect(page.getByText('Fictional demonstration data', { exact: true })).toHaveCount(0);
  await expect(page.locator('article')).toContainText('Government-sourced');
  await page.goto(`./?mode=local-v2#/locations/${record?.facility_id}?profile=curated`);
  await expect(page.getByRole('heading', { name: record?.canonical_name ?? '' })).toBeVisible();
  await expect(page.locator('article')).toContainText('Project approval');
});

test.skip(process.env.TEST_RELEASE_E2E !== '1', 'Set TEST_RELEASE_E2E=1 with a disposable guarded test-release backend');

test('renders the guarded disposable test release without public fallback', async ({ page }) => {
  const apiUrl = process.env.UEC_E2E_API_URL ?? 'http://127.0.0.1:8000';
  const token = process.env.UEC_TEST_RELEASE_TOKEN ?? process.env.UEC_DEV_PREVIEW_TOKEN;
  expect(token, 'UEC_TEST_RELEASE_TOKEN must be supplied in memory by the test runner').toBeTruthy();
  const probe = await fetch(`${apiUrl}/api/dev/preview/test-release/locations?profile=official&limit=100`, { headers: { 'X-UEC-Dev-Preview-Token': token ?? '' } });
  expect(probe.ok).toBeTruthy();
  const body = await probe.json() as { data?: Array<{ canonical_name?: string }> };
  expect(body.data?.length).toBeGreaterThan(0);
  await page.route('**/api/dev/preview/test-release/**', async route => {
    const requestUrl = new URL(route.request().url());
    const upstream = await fetch(`${apiUrl}${requestUrl.pathname}${requestUrl.search}`, { headers: { 'X-UEC-Dev-Preview-Token': token ?? '' } });
    await route.fulfill({ status: upstream.status, headers: Object.fromEntries(upstream.headers.entries()), body: await upstream.text() });
  });
  await page.goto('./?preview=test-release#/');
  await page.getByLabel('Operator token (memory only)').fill(token ?? '');
  await page.getByRole('button', { name: 'Load test release' }).click();
  await expect(page.getByText('Disposable test release — not project-approved or published')).toBeVisible();
  await expect(page.getByRole('button', { name: /Download test-only CSV/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /Preview export/ })).toHaveCount(0);
});
