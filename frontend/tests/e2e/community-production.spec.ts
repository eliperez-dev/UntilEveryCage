import { expect, test } from '@playwright/test';

// This suite is intentionally opt-in. It is for a production-shaped origin
// whose cleanup is performed by the orchestrator with a restricted credential.
// Do not add tracing, screenshots, console logging, or test attachments here:
// the submission tracking capability is private.
test.use({ trace: 'off', screenshot: 'off', video: 'off' });

const origin = process.env.UEC_COMMUNITY_ORIGIN;
const cleanupCredential = process.env.UEC_COMMUNITY_OPERATOR_TOKEN;
test.skip(!origin || !cleanupCredential, 'Set the isolated community origin and cleanup credential to run production acceptance.');

type LocationEnvelope = { data?: Array<{ id?: string; facility_id?: string }> | { locations?: Array<{ id?: string; facility_id?: string }> }; locations?: Array<{ id?: string; facility_id?: string }> };

async function releasedIds(request: import('@playwright/test').APIRequestContext): Promise<[string, string]> {
  const response = await request.get(`${origin}/api/v2/locations?limit=2`);
  expect(response.ok()).toBeTruthy();
  const payload = await response.json() as LocationEnvelope;
  const rows = Array.isArray(payload.data) ? payload.data : payload.data?.locations ?? payload.locations ?? [];
  const ids = rows.map(row => row.id ?? row.facility_id).filter((id): id is string => typeof id === 'string');
  expect(ids).toHaveLength(2);
  return [ids[0]!, ids[1]!];
}

test('all five contribution types submit and track through the enabled production path', async ({ page, request }) => {
  const [firstId, secondId] = await releasedIds(request);
  const tag = `acceptance-${Date.now()}`;
  const routes: Array<{ path: string; fill: (index: number) => Promise<void> }> = [
    { path: 'facility', fill: async index => { await page.getByLabel('Facility name').fill(`${tag}-facility-${index}`); } },
    { path: 'evidence', fill: async () => { await page.getByLabel('Record link or ID').fill(firstId); await page.getByLabel('What did you find?').fill(`${tag} evidence`); } },
    { path: 'correction', fill: async () => { await page.getByLabel('Record ID').fill(firstId); await page.getByLabel('What should be corrected?').fill(`${tag} correction`); } },
    { path: 'duplicate', fill: async () => { await page.getByLabel('Record ID', { exact: true }).fill(firstId); await page.getByLabel('Possible duplicate record ID').fill(secondId); } },
    { path: 'privacy-removal', fill: async () => { await page.getByLabel('Record ID').fill(firstId); await page.getByLabel('What should we review?').fill(`${tag} privacy review`); } },
  ];

  for (const [index, route] of routes.entries()) {
    await page.goto(`${origin}/#/contribute/${route.path}`);
    await expect(page.getByRole('heading', { name: route.path === 'facility' ? 'Add a facility' : /.*/ })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Send for review' })).toBeVisible();
    await route.fill(index);
    await page.getByLabel(/I have permission to share/).check();
    await page.getByRole('button', { name: 'Send for review' }).click();
    const tracker = page.getByRole('link', { name: 'Track submission', exact: true });
    await expect(tracker).toBeVisible();
    await tracker.click();
    await expect(page.locator('.status-result')).toBeVisible();
  }
});
