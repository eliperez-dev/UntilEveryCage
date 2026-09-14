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

test('test-release mode uses the existing list/detail flow with a private release label', async ({ page }) => {
  await page.route('**/api/dev/preview/test-release/locations.csv**', route => route.fulfill({ headers: { 'content-type': 'text/csv', 'x-uec-test-release': 'true', 'x-uec-release-id': 'test-release' }, body: 'facility_id,project_approval\nfacility-1,pending\n' }));
  await page.route('**/api/dev/preview/test-release/locations**', route => route.fulfill({ json: { data: [{ facility_id: '550e8400-e29b-41d4-a716-446655440000', canonical_name: 'Pending test-release row', city: null, country_code: 'GB', category: 'dairy', source_type: 'official', publication_profile: 'official', factual_review_status: 'unreviewed', privacy_screening_status: 'passed', project_approval: 'pending', reviewer_role: null, publication_warning: null, display_precision: 'unmapped', latitude: null, longitude: null, first_observed_at: null, last_observed_at: null, observation_count: null, lifecycle_status: 'status_unknown', provenance_source_id: 'source-1', provenance_source_name: 'Test source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z', release_id: 'test-release', release_ruleset_version: 'rules-1' }], meta: { api_version: 'dev-test-v1', environment: 'test-only', test_only: true, private_preview: true, release_status: 'candidate', release_id: 'test-release', profile: 'official', coverage_scope: 'test_release_public_shaped_rows', count_semantics: 'Rows only', preview_label: 'Disposable test release — not project-approved or published', result_count: 1, next_cursor: null } } }));
  await page.goto('./?preview=test-release#/');
  await page.getByLabel('Operator token (memory only)').fill('synthetic-test-token');
  await page.getByRole('button', { name: 'Load test release' }).click();
  await expect(page.getByRole('heading', { name: 'Pending test-release row' })).toBeVisible();
  await expect(page.getByText('Disposable test release — not project-approved or published')).toBeVisible();
  await expect(page.getByText('No publishable map location')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Download test-only CSV' })).toBeVisible();
  const csvRequest = page.waitForRequest(request => request.url().includes('/api/dev/preview/test-release/locations.csv'));
  await page.getByRole('button', { name: 'Download test-only CSV' }).click();
  expect((await csvRequest).headers()['x-uec-dev-preview-token']).toBe('synthetic-test-token');
  await expect(page.getByRole('button', { name: /Preview export/ })).toHaveCount(0);
});
