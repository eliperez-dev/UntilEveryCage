import { test, expect } from '@playwright/test';

test.skip(process.env.LOCAL_V2_E2E !== '1', 'Set LOCAL_V2_E2E=1 to run against the real local backend');

test('renders the real seeded local V2 record and opens its detail route', async ({ page }) => {
  const fixtureNames = ['North Star Cooperative', 'River Meadow Foods', 'Quiet Field Holdings'];
  let list: { data?: Array<{ facility_id: string; canonical_name: string }> } = {};
  const response = await fetch('http://127.0.0.1:8000/api/v2/locations?profile=official&limit=1');
  expect(response.ok).toBeTruthy();
  list = await response.json() as typeof list;
  const record = list.data?.[0];
  expect(record?.facility_id).toBeTruthy();
  expect(record?.canonical_name).toBeTruthy();
  await page.goto('./?mode=local-v2&api=http%3A%2F%2F127.0.0.1%3A8000#/');
  await expect(page.getByRole('heading', { name: record?.canonical_name ?? '' })).toBeVisible();
  for (const name of fixtureNames) await expect(page.getByText(name, { exact: true })).toHaveCount(0);
  await page.goto(`./?mode=local-v2&api=http%3A%2F%2F127.0.0.1%3A8000#/locations/${record?.facility_id}?profile=curated`);
  await expect(page.getByRole('heading', { name: record?.canonical_name ?? '' })).toBeVisible();
});
