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

test('all contribution types, including bug reports, submit and track through the enabled production path', async ({ page, request }) => {
  const [firstId, secondId] = await releasedIds(request);
  const tag = `acceptance-${Date.now()}`;
  const owned: Array<{ id: string; secret: string }> = [];
  const routes: Array<{ path: string; fill: (index: number) => Promise<void>; submitLabel: string; trackingLabel: string }> = [
    { path: 'facility', fill: async index => { await page.getByLabel('Facility name').fill(`${tag}-facility-${index}`); await page.getByLabel('Primary activity (optional)').selectOption('slaughter'); }, submitLabel: 'Send for review', trackingLabel: 'Track submission' },
    { path: 'evidence', fill: async () => { await page.getByLabel('Record link or ID').fill(firstId); await page.getByLabel('What did you find?').fill(`${tag} evidence`); }, submitLabel: 'Send for review', trackingLabel: 'Track submission' },
    { path: 'correction', fill: async () => { await page.getByLabel('Record ID').fill(firstId); await page.getByLabel('What should be corrected?').fill(`${tag} correction`); }, submitLabel: 'Send for review', trackingLabel: 'Track submission' },
    { path: 'duplicate', fill: async () => { await page.getByLabel('Record ID', { exact: true }).fill(firstId); await page.getByLabel('Possible duplicate record ID').fill(secondId); }, submitLabel: 'Send for review', trackingLabel: 'Track submission' },
    { path: 'privacy-removal', fill: async () => { await page.getByLabel('Record ID').fill(firstId); await page.getByLabel('What should we review?').fill(`${tag} privacy review`); }, submitLabel: 'Send for review', trackingLabel: 'Track submission' },
    { path: 'bug', fill: async () => { await page.getByLabel('What happened?').fill(`${tag} bug report`); await page.getByLabel('Steps to reproduce').fill('Synthetic acceptance steps'); }, submitLabel: 'Send report', trackingLabel: 'Track report' },
  ];
  const headingByPath: Record<string, string> = {
    facility: 'Add a facility', evidence: 'Add evidence', correction: 'Suggest a correction',
    duplicate: 'Report a duplicate', 'privacy-removal': 'Privacy or removal', bug: 'Report a bug',
  };

  try {
    for (const [index, route] of routes.entries()) {
      await page.goto(`${origin}/#/contribute/${route.path === 'bug' ? 'bug' : route.path}`);
      await expect(page.getByRole('heading', { name: headingByPath[route.path], exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: route.submitLabel })).toBeVisible();
      await route.fill(index);
      if (route.path !== 'bug') await page.getByLabel(/I have permission to share/).check();
      const submitted = page.waitForResponse(response => response.url().endsWith('/api/community/submissions') && response.request().method() === 'POST');
      await page.getByRole('button', { name: route.submitLabel }).click();
      const response = await submitted;
      if (route.path === 'facility') expect(response.request().postDataJSON()).toMatchObject({ claimed_activity: 'slaughter' });
      const receipt = await response.json() as { submission_id: string; receipt_secret: string };
      owned.push({ id: receipt.submission_id, secret: receipt.receipt_secret });
      const tracker = page.getByRole('link', { name: route.trackingLabel, exact: true });
      await expect(tracker).toBeVisible();
      await tracker.click();
      await expect(page.locator('.status-result')).toBeVisible();
    }
    expect(owned.length).toBe(routes.length);
  } finally {
    for (const receipt of owned) {
      const removed = await request.post(`${origin}/api/private/community/submissions/${encodeURIComponent(receipt.id)}/disposition`, {
        headers: { Authorization: `Bearer ${cleanupCredential}`, 'Content-Type': 'application/json' },
        data: { action: 'remove', reason_code: 'privacy' },
      });
      expect(removed.ok()).toBeTruthy();
      const revoked = await request.post(`${origin}/api/community/status`, { data: { submission_id: receipt.id, receipt_secret: receipt.secret } });
      expect(revoked.status()).toBe(404);
    }
  }
});
