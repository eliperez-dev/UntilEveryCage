import { test, expect, type BrowserContext, type Page } from '@playwright/test';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import AxeBuilder from '@axe-core/playwright';

test.skip(process.env.UEC_SECURE_RELAY_BROWSER !== 'true', 'Requires the explicitly enabled local preview and owned disposable relay.');
test.use({ trace: 'off' });
test('real encrypted UI journey: submit, reviewer reply, fresh recovery, contributor reply, close and removal', async ({ browser, baseURL }) => {
  test.setTimeout(90_000);
  expect(new URL(baseURL!).hostname).toBe('127.0.0.1');
  const dir = resolve('../target/secure-inbox-integration');
  const bootstrap = JSON.parse(await readFile(resolve(dir, 'public-bootstrap.json'), 'utf8')) as { reviewer_fingerprint: string; operator_token: string };
  const reviewer = JSON.parse(await readFile(resolve(dir, 'local-reviewer-recovery.json'), 'utf8')) as { encryptedExport: string; recoverySecret: string };
  const screenshots = process.env.UEC_SECURE_SCREENSHOTS ?? resolve(dir, 'screenshots');
  await mkdir(screenshots, { recursive: true });
  const contexts: BrowserContext[] = [], bodies: string[] = [], requestURLs: string[] = [], browserErrors: string[] = [];
  async function context(width: number, height = 1000) {
    const value = await browser.newContext({ baseURL, viewport: { width, height }, colorScheme: 'dark' }); contexts.push(value);
    await value.route('**/api/v2/releases/manifest?profile=community', route => route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }));
    // Any accidental legacy plaintext POST fails the journey rather than reaching a service.
    await value.route('**/api/**', async route => {
      const request = route.request(); requestURLs.push(request.url());
      if (request.method() === 'POST') { expect(new URL(request.url()).pathname).toContain('/community/secure/'); bodies.push(request.postData() ?? ''); }
      await route.fallback();
    });
    value.on('page', page => { page.on('pageerror', error => browserErrors.push(error.name)); });
    return value;
  }
  async function fits(page: Page) { expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true); }
  async function storageHasNoSecrets(page: Page, secrets: string[]) {
    const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
    for (const value of secrets) expect(storage.includes(value)).toBe(false);
    expect(storage).not.toContain('PRIVATE KEY');
  }
  let caseId = '', recoverySecret = '', privateHref = '';
  try {
    const contributorContext = await context(1440), contributor = await contributorContext.newPage();
    await contributor.goto('/#/contribute');
    await contributor.getByLabel('Facility name', { exact: false }).fill('Synthetic browser encrypted facility');
    await contributor.getByLabel('Additional context (optional)', { exact: true }).fill('Synthetic browser private description');
    await contributor.getByRole('checkbox', { name: 'I have permission to share this information.' }).check();
    await contributor.getByRole('button', { name: 'Send for review' }).click();
    await expect(contributor.getByRole('heading', { name: 'Submission received', exact: true })).toBeVisible();
    caseId = (await contributor.locator('.secure-receipt .reference span').innerText()).trim();
    expect(caseId).toMatch(/^[0-9a-f-]{36}$/);
    const ownedCases = await readFile(resolve(dir, 'browser-owned-cases.json'), 'utf8').then(text => JSON.parse(text) as string[]).catch(() => [] as string[]);
    await writeFile(resolve(dir, 'browser-owned-cases.json'), JSON.stringify([...new Set([...ownedCases, caseId])]));
    recoverySecret = await contributor.getByLabel('Recovery key', { exact: true }).inputValue();
    privateHref = (await contributor.getByRole('link', { name: 'Open private inbox' }).getAttribute('href'))!;
    const downloadPromise = contributor.waitForEvent('download');
    await contributor.getByRole('button', { name: 'Download recovery file', exact: true }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`uec-inbox-${caseId}.asc`);
    const recoveryPath = resolve(dir, `browser-recovery-${caseId}.asc`); await download.saveAs(recoveryPath);
    await expect(contributor.getByRole('status').filter({ hasText: 'Download requested.' })).toBeVisible();
    await fits(contributor); await contributor.screenshot({ path: resolve(screenshots, 'secure-receipt-1440-dark.png'), fullPage: true });
    await storageHasNoSecrets(contributor, [recoverySecret, reviewer.recoverySecret, 'Synthetic browser private description']);
    await contributor.getByRole('link', { name: 'Open private inbox' }).click();
    await expect(contributor.getByRole('heading', { name: 'Submitted information' })).toBeVisible();
    await expect(contributor.getByText('Synthetic browser private description', { exact: true })).toBeVisible();
    // SPA navigation retains the in-memory key; a fresh device below must recover it.
    await contributor.getByRole('link', { name: 'Back to Contribute' }).click();
    await contributor.getByRole('link', { name: 'Track a submission' }).click();
    // Generic tracking has no case: using the saved private link finds the remembered handle.
    await contributor.goto(`/${privateHref}`);
    // Same-document fragment navigation finds the remembered handle.
    await expect(contributor.getByRole('heading', { name: 'Submitted information' })).toBeVisible();

    const reviewContext = await context(1024), review = await reviewContext.newPage();
    await review.goto('/#/secure-review');
    await review.getByLabel('Reviewer access token', { exact: true }).fill(bootstrap.operator_token);
    await review.getByRole('button', { name: 'Open review queue', exact: true }).click();
    await expect(review.getByRole('button', { name: new RegExp(caseId.slice(0, 8)) })).toBeVisible();
    await review.getByLabel('Encrypted reviewer key file', { exact: true }).setInputFiles({ name: 'synthetic-reviewer.asc', mimeType: 'text/plain', buffer: Buffer.from(reviewer.encryptedExport) });
    await review.getByLabel('Recovery key', { exact: true }).fill(reviewer.recoverySecret);
    await review.getByRole('button', { name: 'Unlock key locally', exact: true }).click();
    await expect(review.getByText('Reviewer key unlocked', { exact: false })).toBeVisible();
    await review.getByRole('button', { name: new RegExp(caseId.slice(0, 8)) }).click();
    await expect(review.getByText('Synthetic browser private description', { exact: true })).toBeVisible();
    await review.getByLabel('Reply to contributor', { exact: true }).fill('Synthetic browser reviewer question');
    await review.getByRole('button', { name: 'Send encrypted reply', exact: true }).click();
    await expect(review.getByText('Synthetic browser reviewer question', { exact: true })).toBeVisible();
    await review.getByRole('button', { name: 'More information needed', exact: true }).click();
    await expect(review.locator('.processing-status')).toContainText('More information needed');
    await review.getByRole('switch', { name: 'Dark theme' }).count().then(async count => { if (count) await review.getByRole('switch', { name: 'Dark theme' }).uncheck(); });
    await fits(review); await review.screenshot({ path: resolve(screenshots, 'secure-review-1024.png'), fullPage: true });
    await storageHasNoSecrets(review, [bootstrap.operator_token, reviewer.recoverySecret, recoverySecret]);
    await contributorContext.close();

    const freshContext = await context(390, 844), fresh = await freshContext.newPage();
    await fresh.goto(`/${privateHref}`);
    await fresh.getByLabel('Recovery file', { exact: true }).setInputFiles(recoveryPath);
    await fresh.getByLabel('Recovery key', { exact: true }).fill(recoverySecret);
    await fresh.getByRole('button', { name: 'Open inbox', exact: true }).click();
    await expect(fresh.getByText('Synthetic browser reviewer question', { exact: true })).toBeVisible();
    await expect(fresh.locator('.status-bar strong')).toHaveText('More information needed');
    await fits(fresh); await fresh.screenshot({ path: resolve(screenshots, 'secure-inbox-390-dark.png'), fullPage: true });
    const accessibility = await new AxeBuilder({ page: fresh }).include('.secure-inbox').analyze();
    expect(accessibility.violations.map(row => row.id)).toEqual([]);
    await fresh.getByLabel('Reply to reviewer', { exact: true }).fill('Synthetic browser contributor answer');
    await fresh.getByRole('button', { name: 'Send encrypted reply', exact: true }).click();
    await expect(fresh.getByText('Synthetic browser contributor answer', { exact: true })).toBeVisible();
    await fresh.getByRole('button', { name: 'Refresh inbox', exact: true }).click();
    await expect(fresh.getByText('Synthetic browser contributor answer', { exact: true })).toBeVisible();
    await review.getByRole('button', { name: 'Refresh inbox', exact: true }).click();
    await expect(review.getByText('Synthetic browser contributor answer', { exact: true })).toBeVisible();
    await review.getByRole('button', { name: 'Closed', exact: true }).click();
    await expect(review.locator('.processing-status')).toContainText('Closed');
    await fresh.getByRole('button', { name: 'Refresh inbox', exact: true }).click();
    await expect(fresh.getByText('This inbox is closed to new replies.', { exact: true })).toBeVisible();
    await expect(fresh.getByRole('button', { name: 'Send encrypted reply', exact: true })).toHaveCount(0);
    await storageHasNoSecrets(fresh, [bootstrap.operator_token, reviewer.recoverySecret, recoverySecret, 'Synthetic browser contributor answer']);
    for (const body of bodies) {
      for (const secret of ['Synthetic browser encrypted facility', 'Synthetic browser private description', 'Synthetic browser reviewer question', 'Synthetic browser contributor answer', recoverySecret, reviewer.recoverySecret, 'PRIVATE KEY']) expect(body.includes(secret)).toBe(false);
    }
    const accessSecret = new URLSearchParams(privateHref.split('?')[1]).get('access_secret')!;
    expect(requestURLs.every(value => !value.includes(accessSecret) && !value.includes(bootstrap.operator_token))).toBe(true);
    await review.getByRole('button', { name: 'Remove this inbox', exact: true }).click();
    await review.getByRole('button', { name: 'Confirm inbox removal', exact: true }).click();
    await expect(review.getByRole('heading', { name: 'Submission inbox', exact: true })).toHaveCount(0);
    await fresh.getByRole('button', { name: 'Refresh inbox', exact: true }).click();
    await expect(fresh.getByText('Synthetic browser private description', { exact: true })).toHaveCount(0);
    await expect(fresh.getByRole('alert')).toBeVisible();
    expect(browserErrors).toEqual([]);
  } finally { await Promise.all(contexts.map(value => value.close().catch(() => undefined))); }
});
