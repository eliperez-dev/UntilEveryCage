import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
const recordId = '27d7ef4b-39de-4d9f-bacc-4062f560321e';
const submissionId = '18c6ef3a-28cd-4c8e-a9bb-3951f45f210d';
const secret = 'synthetic-mobile-receipt';
const map = '#/map?lat=44.5&lon=8.1&z=5&release_id=synthetic-release';
async function setup(page: Page, options: { enabled?: boolean } = {}) {
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    return url.protocol.startsWith('http') && !['127.0.0.1', 'localhost'].includes(url.hostname) ? route.abort() : route.fallback();
  });
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith('/api/')) return route.fallback();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/community/capabilities') return json({ enabled: options.enabled !== false, types: ['facility', 'evidence', 'correction', 'duplicate', 'privacy_removal'] });
    if (path === '/api/community/submissions') return json({ submission_id: submissionId, receipt_secret: secret, status: 'received' }, 201);
    if (path === '/api/community/status') return json({ submission_id: submissionId, status: 'held' });
    if (path === `/api/v2/locations/${recordId}`) return json({ api_version: 'v2', data: { facility_id: recordId, canonical_name: 'Synthetic Riverside Processing and Storage Facility', city: 'Sample town', country_code: 'DK', category: 'processing_and_preparation', display_precision: 'unmapped', latitude: null, longitude: null, source_type: 'official', publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved', reviewer_role: null, publication_warning: null, first_observed_at: null, last_observed_at: '2026-01-01T00:00:00Z', observation_count: 1, lifecycle_status: 'active_observed', provenance_source_id: 'synthetic.source', provenance_source: null, provenance_source_name: 'Synthetic authority', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z', source_rights_status: 'cleared', release_id: 'synthetic-release', release_ruleset_version: 'synthetic-rules' }, meta: { profile: 'official', release_id: 'synthetic-release', ruleset_version: 'synthetic-rules', release_created_at: '2026-01-01T00:00:00Z' } });
    return json({}, 404);
  });
}
const chooser = (page: Page) => page.locator('#contribution-task');
const subtype = (page: Page, name: string) => page.getByRole('navigation', { name: 'Type of update' }).getByRole('link', { name, exact: true });

test('mobile task chooser preserves draft, target, update subtype and return-map context', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await setup(page);
  await page.goto(`#/contribute?type=correction&target=${recordId}&map=${encodeURIComponent(map)}`);
  await expect(chooser(page)).toHaveValue('correction');
  await page.locator('textarea[name=description]').fill('Synthetic correction retained between tasks.');
  await subtype(page, 'Evidence').click();
  await page.locator('textarea[name=description]').fill('Synthetic supporting evidence.');
  await chooser(page).selectOption('facility');
  await page.locator('input[name=label]').fill('Synthetic new facility');
  await chooser(page).selectOption('bug');
  await page.locator('textarea[name=description]').fill('Synthetic interface issue');
  await chooser(page).selectOption('correction');
  await expect(page.locator('textarea[name=description]')).toHaveValue('Synthetic correction retained between tasks.');
  await expect(page.locator('#intake-target')).toHaveValue(recordId);
  await subtype(page, 'Evidence').click();
  await expect(page.locator('textarea[name=description]')).toHaveValue('Synthetic supporting evidence.');
  await chooser(page).selectOption('privacy_removal');
  await expect(page.locator('#intake-target')).toHaveValue(recordId);
  await expect(page.getByRole('link', { name: 'Back to map', exact: true })).toHaveAttribute('href', map);
  await page.goBack(); await expect(chooser(page)).toHaveValue('correction');
  await expect(page.getByRole('link', { name: 'Evidence', exact: true })).toHaveAttribute('aria-current', 'page');
  await chooser(page).selectOption('facility');
  await expect(page.locator('input[name=label]')).toHaveValue('Synthetic new facility');
  const storage = await page.evaluate(() => JSON.stringify([Object.values(localStorage), Object.values(sessionStorage)]));
  expect(storage).not.toContain('Synthetic');
  expect(new URLSearchParams(new URL(page.url()).hash.split('?')[1]).get('target')).toBe(recordId);
});

test('mobile validation, busy guard, receipt and tracking retain the real flow', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 }); await setup(page);
  let writes = 0; let releaseRequest: (() => void) | undefined;
  await page.route('**/api/community/submissions', async route => {
    writes++; await new Promise<void>(resolve => { releaseRequest = resolve; });
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ submission_id: submissionId, receipt_secret: secret, status: 'received' }) });
  });
  await page.goto('#/contribute');
  await page.getByRole('button', { name: 'Send for review', exact: true }).click();
  await expect(page.locator('input[name=label]')).toBeFocused(); expect(writes).toBe(0);
  await page.locator('input[name=label]').fill('Synthetic mobile submission');
  await page.getByLabel(/I have permission/).check();
  await page.getByRole('button', { name: 'Send for review', exact: true }).click();
  await expect(chooser(page)).toBeDisabled(); await expect.poll(() => writes).toBe(1);
  releaseRequest!();
  await expect(page.getByRole('heading', { name: 'Contribution received', exact: true })).toBeVisible();
  const tracking = page.getByRole('link', { name: 'Track submission', exact: true });
  await expect(tracking).toHaveAttribute('href', `#/contribution-status?submission_id=${submissionId}&receipt_secret=${secret}`);
  const bounds = await tracking.boundingBox(); expect(bounds!.width).toBeGreaterThan(200);
  await tracking.click(); await expect(page.getByRole('heading', { name: 'Awaiting review', exact: true })).toBeVisible();
  expect(writes).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('mobile disabled intake can retry while bug reports remain usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); const options = { enabled: false }; await setup(page, options);
  await page.goto('#/contribute?type=correction');
  await expect(page.getByRole('heading', { name: 'Submissions are unavailable', exact: true })).toBeVisible();
  await chooser(page).selectOption('bug'); await expect(page.locator('textarea[name=steps]')).toBeVisible();
  await chooser(page).selectOption('facility');
  options.enabled = true; await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.locator('input[name=label]')).toBeVisible();
});

test('mobile task and optional field layouts remain readable in both themes and languages', async ({ page }) => {
  test.setTimeout(120_000);
  await setup(page);
  for (const viewport of [{ width: 320, height: 720 }, { width: 390, height: 844 }, { width: 720, height: 960 }, { width: 844, height: 390 }]) {
    for (const theme of ['dark', 'light']) for (const language of ['en', 'es']) {
      await page.setViewportSize(viewport);
      await page.goto('#/contribute');
      await page.evaluate(({ theme, language }) => { localStorage.setItem('uec-theme', theme); localStorage.setItem('uec-language', language); }, { theme, language });
      await page.reload();
      await expect(page.locator('html')).toHaveAttribute('lang', language);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await expect(page.locator('input[name=label]')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(await page.locator('input[name=label]').evaluate(node => parseFloat(getComputedStyle(node).fontSize))).toBeGreaterThanOrEqual(16);
      if (viewport.width <= 720 || viewport.height <= 390) {
        await expect(chooser(page)).toBeVisible();
        const field = await page.locator('input[name=label]').boundingBox(); expect(field!.y).toBeLessThan(380);
        await chooser(page).selectOption('privacy_removal');
        await expect(page.locator('textarea[name=description]')).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      }
    }
  }
});

test('render mobile and desktop contribution states with synthetic records', async ({ page }) => {
  await setup(page); await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`#/contribute?type=correction&target=${recordId}&map=${encodeURIComponent(map)}`);
  await expect(page.locator('.intake')).toBeVisible();
  await expect(page.getByText('Synthetic Riverside Processing and Storage Facility', { exact: true })).toBeVisible();
  await page.locator('textarea[name=description]').fill('The published facility name needs updating. Supporting source linked below.');
  await page.locator('.intake h2').click();
  const output = process.env.UEC_CONTRIBUTION_SCREENSHOT_DIR;
  if (output) {
    await page.screenshot({ path: join(output, 'contribution-mobile.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({ path: join(output, 'contribution-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 320, height: 720 });
    await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
    await page.screenshot({ path: join(output, 'contribution-mobile-light.png'), fullPage: true });
  }
});
