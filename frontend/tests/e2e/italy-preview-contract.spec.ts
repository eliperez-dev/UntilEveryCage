import { test, expect } from '@playwright/test';

const candidateId = '123e4567-e89b-42d3-a456-426614174000';
const candidate = {
  candidate_id: candidateId, source_id: 'it.853-2004', location_class: 'numeric_source_coordinate',
  display_precision: 'approximate_source_precision_unknown_pending_review', country_code: 'IT', city: 'Roma',
  postal_code: null, latitude: 41.9028, longitude: 12.4964, coordinate_precision: 'source-precision-unknown',
  coordinate_review_status: 'pending_human_privacy_review', factual_review_status: 'not_reviewed',
  privacy_screening_status: 'pending', project_approval: false, publication_status: 'not_published',
  preview_label: 'Private real V2 candidate — not project-approved or published',
};

test('Italy preview is read-only, source-scoped, searchable, map-rendered, disclosed, and token-free', async ({ page }) => {
  const calls: string[] = [];
  const requests: string[] = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/dev/real-preview/')) {
      calls.push(`${request.method()} ${url.pathname}`);
      requests.push(request.url());
    }
  });
  await page.route('**/dev/real-preview/**', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    expect(route.request().method()).toBe('GET');
    let body: unknown;
    if (path.endsWith('/counts')) {
      body = { api_version: 'real-preview-v1', data: { facility_candidate_count: 1, numeric_coordinate_count: 1, city_postal_count: 0, map_visible_count: 1 }, meta: { private_preview: true, runtime_ledger: [{ source_id: 'it.853-2004', run_id: 'fixture-run' }] } };
    } else if (path.endsWith('/facets')) {
      body = { api_version: 'real-preview-v1', data: [{ source_id: 'it.853-2004', location_class: 'numeric_source_coordinate', count: 1 }] };
    } else if (path.endsWith('/viewport')) {
      expect(url.searchParams.get('source_id')).toBe('it.853-2004');
      body = { api_version: 'real-preview-v1', data: [candidate], meta: { private_preview: true, next_cursor: null } };
    } else if (path.endsWith(`/locations/${candidateId}`)) {
      body = { api_version: 'real-preview-v1', data: candidate };
    } else if (path.endsWith('/locations')) {
      expect(url.searchParams.get('source_id')).toBe('it.853-2004');
      body = { api_version: 'real-preview-v1', data: [candidate], meta: { private_preview: true, next_cursor: null } };
    } else return route.fulfill({ status: 404, body: 'not found' });
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });

  await page.goto('/#/map?f1a=field&source=it.853-2004&lat=42.5&lon=12.5&z=5');
  await expect(page.locator('[data-data-mode="real-preview"]')).toBeVisible();
  await page.getByRole('searchbox').fill('Roma');
  await expect(page.getByText(/it\.853-2004/).first()).toBeVisible();
  const feature = page.getByRole('button', { name: 'Open approximate source location for it.853-2004' });
  await expect(feature).toBeVisible();
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.querySourceFeatures('locations').some((feature: any) => feature.properties.kind === 'approximate');
  }, undefined, { timeout: 90_000 });
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.queryRenderedFeatures({ layers: ['approximate-points'] }).length ?? 0)).toBeGreaterThan(0);
  await feature.click();
  const detail = page.locator('.reading-sheet');
  await expect(detail.getByRole('heading', { level: 2, name: /it\.853-2004/ })).toBeVisible();
  await expect(detail.getByText('Approximate source coordinate · precision unknown', { exact: true })).toBeVisible();
  await expect(detail.getByText(/private preview only.*not approved or published/i)).toBeVisible();
  expect(calls).not.toContain('POST /dev/real-preview/refresh');
  expect(calls).toContain('GET /dev/real-preview/locations');
  expect(calls).toContain('GET /dev/real-preview/viewport');
  expect(calls).toContain('GET /dev/real-preview/counts');
  expect(calls).toContain(`GET /dev/real-preview/locations/${candidateId}`);
  expect(requests.join('\n')).not.toMatch(/uec-dev-preview-token|postgresql:|password|secret/i);
  expect(await page.locator('body').innerText()).not.toMatch(/uec-dev-preview-token|x-uec-dev-preview-token|postgresql:/i);
});
