import { test, expect } from '@playwright/test';

const preview = {
  api_version: 'dev-preview-v1',
  data: [{ candidate_id: 'candidate-1', source_record_id: 'source-row-1', facility_id: 'facility-1', canonical_name: 'Private candidate facility', country_code: 'DK', city: 'North Coast', category: 'dairy', display_precision: 'unmapped', latitude: null, longitude: null, source_type: 'official', provenance_source_id: 'source-1', provenance_source_name: 'Private synthetic source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z', factual_review_status: 'unreviewed', privacy_screening_status: 'passed', project_approval: false, release_id: 'candidate-release', release_status: 'candidate', preview_label: 'PRIVATE TEST DATA — NOT REVIEWED OR PUBLISHED' }],
  meta: { test_only: true, private_preview: true, profile: null, coverage_scope: 'candidate_release_only', next_cursor: null },
};

test('private preview keeps review semantics and has no public export controls', async ({ page }) => {
  await page.route('**/api/dev/preview/candidates**', route => route.fulfill({ json: preview }));
  await page.goto('./?preview=dev-candidates&mode=local-v2#/');
  await page.getByLabel('Operator token (memory only)').fill('synthetic-test-token');
  await page.getByRole('button', { name: 'Load private candidates' }).click();
  await expect(page.getByRole('heading', { name: 'Private candidate facility' })).toBeVisible();
  await expect(page.getByText('false — not approved')).toBeVisible();
  await expect(page.getByText('null — not published')).toBeVisible();
  await expect(page.getByText('Session note: not inspected')).toBeVisible();
  await expect(page.getByRole('button', { name: /Preview export/ })).toHaveCount(0);
  await expect(page.locator('.phase-controls')).toHaveCount(0);
  await expect(page.getByText('Fictional demonstration data')).toHaveCount(0);
});

test('private preview failure does not fall back to fixture records', async ({ page }) => {
  await page.route('**/api/dev/preview/candidates**', route => route.fulfill({ status: 401, body: JSON.stringify({ error: 'dev_preview_auth_failed' }) }));
  await page.goto('./?preview=dev-candidates&mode=local-v2#/');
  await page.getByLabel('Operator token (memory only)').fill('wrong-token');
  await page.getByRole('button', { name: 'Load private candidates' }).click();
  await expect(page.getByText('Private candidate preview authentication failed.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Private candidate facility' })).toHaveCount(0);
  await expect(page.getByText('Synthetic demonstration')).toHaveCount(0);
});
