import { expect, test } from '@playwright/test';
import { randomUUID } from 'node:crypto';

test('a bug report is saved, available to operators and privately trackable', async ({ page, request }) => {
  test.skip(!process.env.UEC_BUG_REPORT_E2E || !process.env.UEC_COMMUNITY_CLEANUP_TOKEN, 'Requires explicitly authorized intake testing and cleanup credentials.');
  test.setTimeout(90_000);
  const operator = process.env.UEC_COMMUNITY_CLEANUP_TOKEN!;
  const report = {
    description: `UEC automated test; discard ${randomUUID()}`,
    expected_behavior: 'Synthetic expected behavior',
    reproduction_steps: 'Synthetic steps for the automated test',
    page_url: 'https://example.test/synthetic-bug',
  };
  let receipt: { submission_id: string; receipt_secret: string } | undefined;
  try {
    await page.goto('/#/contribute/bug');
    await page.getByLabel('What happened?').fill(report.description);
    await page.getByText('Additional details (optional)', { exact: true }).click();
    await page.getByLabel('What did you expect?').fill(report.expected_behavior);
    await page.getByLabel('Steps to reproduce').fill(report.reproduction_steps);
    await page.getByLabel('Page link (optional)').fill(report.page_url);
    const submitted = page.waitForResponse(response => response.url().endsWith('/api/community/submissions') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Send report', exact: true }).click();
    const response = await submitted;
    expect(response.status()).toBe(201);
    const accepted = await response.json();
    expect(accepted.status).toBe('received');
    receipt = { submission_id: accepted.submission_id, receipt_secret: accepted.receipt_secret };
    await expect(page.getByText('Report saved.', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Send report', exact: true })).toHaveCount(0);
    const queueResponse = await request.get('/api/private/community/submissions?status=received&limit=50', { headers: { Authorization: `Bearer ${operator}` } });
    expect(queueResponse.ok()).toBe(true);
    const queue = await queueResponse.json();
    const saved = queue.submissions.find((item: { submission_id: string }) => item.submission_id === receipt!.submission_id);
    expect(saved?.kind === 'bug' && Object.entries(report).every(([key, value]) => saved[key] === value)).toBe(true);
    expect((await request.get('/api/private/community/submissions')).status()).toBe(404);
    await page.screenshot({ path: '../target/record-repair/hosted-bug-report-saved.png' });
    await page.getByRole('link', { name: 'Track report', exact: true }).click();
    await expect(page.locator('.status-result')).toBeVisible();
  } finally {
    if (receipt) {
      const removed = await request.post(`/api/private/community/submissions/${receipt.submission_id}/disposition`, { headers: { Authorization: `Bearer ${operator}` }, data: { action: 'remove', reason_code: 'other' } });
      expect(removed.ok()).toBe(true);
      expect((await request.post('/api/community/status', { data: receipt })).status()).toBe(404);
    }
  }
});
