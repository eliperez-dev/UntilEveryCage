import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('completed Belgium CLI run is readable in the preview without an operational browser refresh', async ({ page }) => {
  test.setTimeout(180_000);
  const runId = process.env.UEC_E2E_BE_RUN_ID;
  const ledgerPath = process.env.UEC_E2E_BE_LEDGER_PATH;
  test.skip(!runId || !ledgerPath, 'Requires a completed Belgium CLI run and ledger path.');
  const ledger = JSON.parse(await readFile(ledgerPath!, 'utf8'));
  expect(ledger.run_id).toBe(runId);
  expect(ledger.source_id).toBe('be.locations');
  expect(ledger.public_rows).toBe(0);
  const requests: string[] = [];
  page.on('request', request => requests.push(request.url()));
  await page.goto('/#/map?f1a=field&source=be.locations&lat=50.7&lon=4.6&z=8');
  await expect(page.locator('[data-data-mode="real-preview"]')).toBeVisible();
  const counts = await page.evaluate(async () => await (await fetch('/dev/real-preview/counts', { cache: 'no-store' })).json());
  expect(counts.meta.runtime_ledger.some((entry: any) => entry.source_id === 'be.locations' && entry.run_id === runId)).toBe(true);
  await expect(page.getByRole('button', { name: /Open approximate city location/ }).first()).toBeVisible({ timeout: 90_000 });
  await page.getByRole('button', { name: /Open approximate city location/ }).first().click();
  const aggregateMembers = page.locator('#field-record-list ol li button');
  await expect(aggregateMembers.first()).toBeVisible();
  await aggregateMembers.first().click();
  await expect(page.locator('.reading-sheet').getByText(/Approximate city location — not a facility point/)).toBeVisible();
  expect(requests.some(url => new URL(url).pathname === '/dev/real-preview/refresh')).toBe(false);
  expect(requests.join('\n')).not.toMatch(/uec-dev-preview-token|postgresql:|password|secret/i);
});
