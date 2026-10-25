import { expect, test } from '@playwright/test';

test('database starts release facets alongside the first page request', async ({ page }) => {
  let locationsFinished = false;
  let facetsStartedBeforeLocationsFinished = false;
  const releaseId = 'release-parallel-fixture';
  await page.route(url => new URL(url.href).pathname === '/api/v2/locations', async route => {
    await new Promise(resolve => setTimeout(resolve, 300));
    locationsFinished = true;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      api_version: 'v2', data: [], meta: {
        profile: 'official', release_id: releaseId, ruleset_version: 'rules-1', next_cursor: null,
        total_count: 0, coverage_note: 'Synthetic request-order fixture.',
        coverage_scope: 'fixture only', count_semantics: 'fixture only',
      },
    }) });
  });
  await page.route(url => new URL(url.href).pathname === '/api/v2/discovery/facets', async route => {
    facetsStartedBeforeLocationsFinished = !locationsFinished;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      api_version: 'v2', meta: {
        profile: 'official', release_id: releaseId, ruleset_version: 'rules-1',
        release_created_at: '2026-10-18T00:00:00Z', coverage_scope: 'fixture only',
        count_semantics: 'fixture only', filters: {
          country_code: null, region: null, category: null, source_type: null,
          display_precision: null, lifecycle_status: null,
        },
      }, dimensions: { country_code: [], source_id: [] },
    }) });
  });

  await page.goto('./#/database');
  await expect(page.getByRole('heading', { name: 'Browse records' })).toBeVisible();
  await expect.poll(() => facetsStartedBeforeLocationsFinished).toBe(true);
  await expect(page.getByText('0 matching records')).toBeVisible();
});
