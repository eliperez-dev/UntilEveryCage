import { test, expect, type Page } from '@playwright/test';

const firstId = '550e8400-e29b-41d4-a716-446655440000';
const secondId = '550e8400-e29b-41d4-a716-446655440001';
const row = (id = firstId, name = 'First local record', profile: 'official' | 'secondary' | 'community' = 'official') => ({
  facility_id: id, canonical_name: name, city: 'North Coast', country_code: 'DK', category: 'dairy',
  source_type: profile === 'community' ? 'user_submitted' : profile, publication_profile: profile,
  factual_review_status: profile === 'community' ? 'unreviewed' : 'reviewed', privacy_screening_status: 'passed',
  project_approval: profile === 'community' ? 'pending' : 'approved', reviewer_role: null,
  publication_warning: profile === 'community' ? 'Unreviewed community claim — not verified by Until Every Cage' : null,
  display_precision: 'city', latitude: 55, longitude: 10, first_observed_at: null,
  last_observed_at: '2026-01-01T00:00:00Z', observation_count: 1, lifecycle_status: 'active_observed',
  provenance_source_id: 'source-1', provenance_source_name: 'Synthetic local source',
  provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z',
  release_id: 'rel-1', release_ruleset_version: 'rules-1',
});
const list = (profile: 'official' | 'secondary' | 'community', data = [row(firstId, 'First local record', profile)], nextCursor: string | null = null) => ({
  data, api_version: 'v2', meta: { release_id: 'rel-1', ruleset_version: 'rules-1', profile, next_cursor: nextCursor, coverage_note: 'Selected promoted release only.' },
});
const detail = (data: ReturnType<typeof row>, profile: 'official' | 'secondary' | 'community') => ({
  data, api_version: 'v2', meta: { release_id: 'rel-1', ruleset_version: 'rules-1', release_created_at: '2026-01-01T00:00:00Z', profile },
});
const mockMetadata = async (page: Page) => page.route('**/api/v2/discovery/filters', route => route.fulfill({ status: 503, body: 'unavailable' }));

test('community direct link opens in community mode with persistent record context', async ({ page }) => {
  await mockMetadata(page);
  const seen: string[] = [];
  await page.route('**/api/v2/locations**', route => {
    const url = new URL(route.request().url());
    seen.push(url.searchParams.get('profile') ?? 'missing');
    return route.fulfill({ json: url.pathname.endsWith(firstId) ? detail(row(firstId, 'Community claim', 'community'), 'community') : list('community', [row(firstId, 'Community claim', 'community')]) });
  });
  await page.goto(`./?mode=local-v2#/locations/${firstId}?profile=community`);
  await expect(page.getByLabel('Profile')).toHaveValue('community');
  await expect(page.getByRole('note')).toContainText('Not verified by Until Every Cage');
  await expect(page.getByRole('heading', { name: 'Community claim' })).toBeVisible();
  await expect(page.locator('article')).toContainText('Community-submitted');
  await expect(page.locator('article')).toContainText('pending');
  await expect(page.locator('article')).toContainText('Factual reviewunreviewed');
  await page.getByRole('button', { name: 'Show map' }).click();
  await expect(page.locator('.map-warning')).toContainText('Unreviewed community claims');
  expect(seen).toEqual(['community', 'community']);
});

test('first-page-only search reports uncertainty instead of a global no-results claim', async ({ page }) => {
  await mockMetadata(page);
  await page.route('**/api/v2/locations**', route => {
    const q = new URL(route.request().url()).searchParams.get('q');
    return route.fulfill({ json: q ? list('official', [], secondId) : list('official', [row()], secondId) });
  });
  await page.goto('./?mode=local-v2#/');
  await expect(page.getByText('Only the first page is loaded.', { exact: false })).toBeVisible();
  await page.getByLabel('Search locations').fill('later record');
  await expect(page.getByText('Later pages may contain matches.', { exact: false })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Results.*on first page/ })).toBeVisible();
});

test('late list response cannot replace a newer community selection', async ({ page }) => {
  await mockMetadata(page);
  let releaseOfficial: (() => void) | undefined;
  const officialHeld = new Promise<void>(resolve => { releaseOfficial = resolve; });
  await page.route('**/api/v2/locations**', async route => {
    const profile = new URL(route.request().url()).searchParams.get('profile');
    if (profile === 'official') await officialHeld;
    try { await route.fulfill({ json: list(profile === 'community' ? 'community' : 'official', [row(firstId, profile === 'community' ? 'New community claim' : 'Stale official result', profile === 'community' ? 'community' : 'official')]) }); } catch { /* Aborted requests have no browser response to fulfill. */ }
  });
  await page.goto('./?mode=local-v2#/');
  await page.getByLabel('Profile').selectOption('community');
  await expect(page.getByRole('heading', { name: 'New community claim' })).toBeVisible();
  releaseOfficial?.();
  await expect(page.getByRole('heading', { name: 'Stale official result' })).toHaveCount(0);
  await expect(page.getByRole('note')).toContainText('Not verified');
});

test('search is evaluated by the server without claiming global completeness', async ({ page }) => {
  await mockMetadata(page);
  let listRequests = 0;
  let lastQuery = '';
  await page.route('**/api/v2/locations**', async route => {
    listRequests += 1;
    lastQuery = new URL(route.request().url()).searchParams.get('q') ?? '';
    await route.fulfill({ json: list('official', [row(firstId, 'Current filtered result')], secondId) });
  });
  await page.goto('./?mode=local-v2#/');
  await page.getByLabel('Search locations').fill('current');
  await expect(page.getByRole('heading', { name: 'Current filtered result' })).toBeVisible();
  expect(listRequests).toBe(2);
  expect(lastQuery).toBe('current');
  await expect(page).toHaveURL(/q=current/);
});

test('late detail response cannot replace a newer route', async ({ page }) => {
  await mockMetadata(page);
  let releaseFirst: (() => void) | undefined;
  const firstHeld = new Promise<void>(resolve => { releaseFirst = resolve; });
  await page.route('**/api/v2/locations**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith(firstId)) await firstHeld;
    const body = path.endsWith(firstId) ? detail(row(firstId, 'Stale detail'), 'official') : path.endsWith(secondId) ? detail(row(secondId, 'Current detail'), 'official') : list('official', [row(), row(secondId, 'Second local record')]);
    try { await route.fulfill({ json: body }); } catch { /* Aborted request. */ }
  });
  await page.goto('./?mode=local-v2#/');
  await page.getByRole('button', { name: /First local record/ }).click();
  await expect(page.getByText('Loading the selected local record')).toBeVisible();
  await page.evaluate(id => { window.location.hash = `/locations/${id}?profile=curated`; }, secondId);
  await expect(page.getByRole('heading', { name: 'Current detail' })).toBeVisible();
  releaseFirst?.();
  await expect(page.getByRole('heading', { name: 'Stale detail' })).toHaveCount(0);
});

test('detail failure focuses the error heading and offers recovery', async ({ page }) => {
  await mockMetadata(page);
  await page.route('**/api/v2/locations**', route => new URL(route.request().url()).pathname.endsWith(firstId)
    ? route.fulfill({ status: 503, body: 'unavailable' }) : route.fulfill({ json: list('official') }));
  await page.goto('./?mode=local-v2#/');
  await page.getByRole('button', { name: /First local record/ }).click();
  await expect(page.getByRole('heading', { name: 'Could not load local record' })).toBeFocused();
  await expect(page.getByRole('button', { name: 'Try record again' })).toBeVisible();
  await page.getByRole('button', { name: 'Back to results' }).click();
  await expect(page.getByRole('heading', { name: 'First local record' })).toBeVisible();
});

test('secondary profile remains distinct through list, detail, and export requests', async ({ page }) => {
  await mockMetadata(page);
  const secondaryPayload = row(firstId, 'Secondary source record', 'secondary');
  const seen: string[] = [];
  await page.route('**/api/v2/locations*', async route => {
    const url = new URL(route.request().url());
    seen.push(`${url.pathname}|${url.searchParams.get('profile') ?? ''}`);
    await route.fulfill({ json: url.pathname.endsWith(firstId) ? detail(secondaryPayload, 'secondary') : list('secondary', [secondaryPayload]) });
  });
  await page.route('**/api/v2/locations.csv*', route => route.fulfill({ headers: { 'content-type': 'text/csv', 'x-uec-release-id': 'rel-1' }, body: 'facility_id\nsecondary\n' }));
  await page.goto('./?mode=local-v2#/');
  await page.getByLabel('Profile').selectOption('secondary');
  await expect(page.getByRole('heading', { name: 'Secondary source record' })).toBeVisible();
  expect(seen.some(value => value.endsWith('|secondary'))).toBeTruthy();
  await page.getByRole('button', { name: /Download secondary CSV/ }).click();
  await expect(page.locator('.release-panel')).toContainText('secondary');
});

test('malformed V2 envelopes fail closed with a contract-specific state', async ({ page }) => {
  await mockMetadata(page);
  await page.route('**/api/v2/locations**', route => route.fulfill({ json: { api_version: 'v1', data: [] } }));
  await page.goto('./?mode=local-v2#/');
  await expect(page.getByRole('heading', { name: 'Could not load local V2 data' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('V2 data contract unavailable');
  await expect(page.getByRole('button', { name: /North Star Cooperative/ })).toHaveCount(0);
});
