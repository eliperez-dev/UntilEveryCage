import { expect, test, type Page } from '@playwright/test';
import { LANDING_SUMMARY_CACHE_KEY } from '../../src/app/landingSummaryCache';

function gate() {
  let release!: () => void;
  return { promise: new Promise<void>(resolve => { release = resolve; }), release: () => release() };
}
async function install(page: Page) {
  const releaseId = 'synthetic-landing-cache';
  const state = { generation: 1, status: 200, manifestGate: null as ReturnType<typeof gate> | null,
    facetsGate: null as ReturnType<typeof gate> | null, countryGate: null as ReturnType<typeof gate> | null, requests: [] as string[] };
  await page.route('https://**/*', route => route.abort());
  await page.route('**/api/v2/**', async route => {
    const url = new URL(route.request().url()), precision = url.searchParams.get('display_precision');
    state.requests.push(url.pathname);
    if (url.pathname === '/api/v2/releases/manifest') {
      await state.manifestGate?.promise;
      return route.fulfill({ status: state.status, json: state.status === 200 ? { api_version: 'v2', data: {
        profile: 'official', release_id: releaseId, manifest: {}, manifest_sha256: 'a'.repeat(64), suppression_generation: state.generation,
      } } : {} }).catch(() => {});
    }
    if (url.pathname === '/api/v2/discovery/facets') {
      expect(url.searchParams.get('release_id')).toBe(releaseId);
      if (precision) await state.countryGate?.promise; else await state.facetsGate?.promise;
      const dimensions = precision ? {
        display_precision: [{ value: precision, count: precision === 'source_reported' ? 5 : 2 }],
        country_code: precision === 'source_reported' ? [{ value: 'DK', count: 4 }, { value: 'US', count: 1 }] : [{ value: 'DK', count: 2 }],
      } : {
        display_precision: [{ value: 'source_reported', count: 5 }, { value: 'approximate', count: 2 }, { value: 'city', count: 3 }, { value: 'unmapped', count: 1 }],
        source_id: [{ value: 'synthetic-a', count: 7 }, { value: 'synthetic-b', count: 4 }],
      };
      return route.fulfill({ json: { api_version: 'v2', meta: { profile: 'official', release_id: releaseId, ruleset_version: 'synthetic-rules',
        release_created_at: '2026-01-01T00:00:00Z', coverage_scope: 'Synthetic public aggregate', count_semantics: 'Synthetic records',
        filters: precision ? { display_precision: precision } : {} }, dimensions } }).catch(() => {});
    }
    return route.fulfill({ status: 404, json: {} });
  });
  return state;
}
const stored = (page: Page) => page.evaluate(key => localStorage.getItem(key), LANDING_SUMMARY_CACHE_KEY);
const facetsRequests = (state: Awaited<ReturnType<typeof install>>) => state.requests.filter(path => path.endsWith('/facets')).length;

test('landing persists complete aggregates across reload, checks eligibility before paint and skips warm facets', async ({ page }) => {
  const state = await install(page); state.countryGate = gate();
  await page.goto('./');
  await expect(page.locator('.release-totals dd')).toHaveText(['11', '7', '2', 'Loading…']);
  expect(await stored(page)).toBeNull();
  state.countryGate.release();
  await expect(page.locator('.release-totals dd')).toHaveText(['11', '7', '2', '2']);
  await expect.poll(() => stored(page)).not.toBeNull();
  const before = facetsRequests(state), requestsBefore = state.requests.length;
  state.manifestGate = gate();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Loading release totals…', { exact: true })).toBeVisible();
  await expect(page.locator('.release-totals')).toHaveCount(0);
  await expect.poll(() => state.requests.length).toBe(requestsBefore + 1);
  expect(facetsRequests(state)).toBe(before);
  state.manifestGate.release();
  await expect(page.locator('.release-totals dd')).toHaveText(['11', '7', '2', '2']);
  expect(facetsRequests(state)).toBe(before);
  expect(state.requests.every(path => ['/api/v2/releases/manifest', '/api/v2/discovery/facets'].includes(path))).toBe(true);
});

test('landing invalidates changed restrictions before new facets and clears unavailable cached releases', async ({ page }) => {
  const state = await install(page);
  await page.goto('./');
  await expect(page.locator('.release-totals dd')).toHaveText(['11', '7', '2', '2']);
  await expect.poll(() => stored(page)).not.toBeNull();
  const before = facetsRequests(state);
  state.generation = 2; state.facetsGate = gate();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect.poll(() => facetsRequests(state)).toBe(before + 1);
  await expect(page.getByText('Loading release totals…', { exact: true })).toBeVisible();
  await expect(page.locator('.release-totals')).toHaveCount(0);
  expect(await stored(page)).toBeNull();
  state.facetsGate.release();
  await expect(page.locator('.release-totals dd')).toHaveText(['11', '7', '2', '2']);
  await expect.poll(async () => JSON.parse((await stored(page)) ?? '{}').identity?.suppressionGeneration).toBe(2);
  const checkedFacets = facetsRequests(state);
  state.status = 404;
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Release totals are unavailable.', { exact: true })).toBeVisible();
  await expect(page.locator('.release-totals')).toHaveCount(0);
  expect(await stored(page)).toBeNull(); expect(facetsRequests(state)).toBe(checkedFacets);
});
