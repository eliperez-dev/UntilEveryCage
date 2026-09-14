import { test, expect, type Page } from '@playwright/test';

const firstId = '550e8400-e29b-41d4-a716-446655440000';
const secondId = '550e8400-e29b-41d4-a716-446655440001';
const row = (id = firstId, name = 'First local record', profile: 'official' | 'community' = 'official') => ({
  facility_id: id, canonical_name: name, city: 'North Coast', country_code: 'DK', category: 'dairy',
  source_type: profile === 'community' ? 'user_submitted' : 'official', publication_profile: profile,
  factual_review_status: profile === 'community' ? 'unreviewed' : 'reviewed', privacy_screening_status: 'passed',
  project_approval: profile === 'community' ? 'pending' : 'approved', reviewer_role: null,
  publication_warning: profile === 'community' ? 'Unreviewed community claim — not verified by Until Every Cage' : null,
  display_precision: 'city', latitude: 55, longitude: 10, first_observed_at: null,
  last_observed_at: '2026-01-01T00:00:00Z', observation_count: 1, lifecycle_status: 'active_observed',
  provenance_source_id: 'source-1', provenance_source_name: 'Synthetic local source',
  provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z',
  release_id: 'rel-1', release_ruleset_version: 'rules-1',
});
const list = (profile: 'official' | 'community', data = [row(firstId, 'First local record', profile)], nextCursor: string | null = null) => ({
  data, api_version: 'v2', meta: { release_id: 'rel-1', ruleset_version: 'rules-1', profile, next_cursor: nextCursor, coverage_note: 'Selected promoted release only.' },
});
const detail = (data: ReturnType<typeof row>, profile: 'official' | 'community') => ({
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
  await page.route('**/api/v2/locations**', route => route.fulfill({ json: list('official', [row()], secondId) }));
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

test('changing search while a list is pending invalidates the old response', async ({ page }) => {
  await mockMetadata(page);
  let releaseFirst: (() => void) | undefined;
  const firstHeld = new Promise<void>(resolve => { releaseFirst = resolve; });
  let listRequests = 0;
  await page.route('**/api/v2/locations**', async route => {
    const index = ++listRequests;
    if (index === 1) await firstHeld;
    try { await route.fulfill({ json: list('official', [row(firstId, index === 1 ? 'Stale initial result' : 'Current filtered result')]) }); } catch { /* Aborted request. */ }
  });
  await page.goto('./?mode=local-v2#/');
  await page.getByLabel('Search locations').fill('current');
  await expect(page.getByRole('heading', { name: 'Current filtered result' })).toBeVisible();
  releaseFirst?.();
  await expect(page.getByRole('heading', { name: 'Stale initial result' })).toHaveCount(0);
  expect(listRequests).toBeGreaterThanOrEqual(2);
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
