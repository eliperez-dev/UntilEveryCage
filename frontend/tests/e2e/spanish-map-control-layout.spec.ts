import { expect, test, type Page } from '@playwright/test';

const releaseId = 'synthetic-spanish-layout-release';
const facilityId = '550e8400-e29b-41d4-a716-446655440000';
const observedAt = '2026-01-01T00:00:00Z';
const ruleset = 'synthetic-spanish-rules';
const releaseMeta = {
  release_id: releaseId, ruleset_version: ruleset, release_created_at: observedAt, profile: 'official',
  coverage_note: 'Synthetic fixture only.', coverage_scope: 'synthetic fixture', count_semantics: 'Synthetic test rows only.',
};
const row = {
  facility_id: facilityId, canonical_name: 'Synthetic Spanish layout facility', city: 'Synthetic locality', country_code: 'DK',
  category: 'processing_and_preparation', source_type: 'official', publication_profile: 'official',
  factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved', reviewer_role: null,
  publication_warning: null, display_precision: 'source_reported', latitude: 55, longitude: 10,
  first_observed_at: null, last_observed_at: observedAt, observation_count: 1, lifecycle_status: 'active_observed',
  provenance_source_id: 'synthetic-spanish-source', provenance_source: null, provenance_source_name: 'Synthetic source',
  provenance_source_url: 'https://example.test/source', provenance_retrieved_at: observedAt, source_rights_status: 'cleared',
  release_id: releaseId, release_ruleset_version: ruleset, taxonomy_display_category: 'processing_and_preparation',
  taxonomy_primary_categories: ['processing_and_preparation'],
};

async function mockSanitizedApi(page: Page) {
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  await page.route('https://server.arcgisonline.com/**', route => route.abort());
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (!path.startsWith('/api/')) return route.fallback();
    let body: unknown = {};
    if (path === '/api/v2/releases/manifest') {
      body = { api_version: 'v2', data: { release_id: releaseId, profile: 'official', manifest: {}, manifest_sha256: 'a'.repeat(64), suppression_generation: 1 } };
    } else if (path === '/api/v2/locations') {
      body = { api_version: 'v2', data: [row], meta: { ...releaseMeta, total_count: 1, next_cursor: null } };
    } else if (path === '/api/v2/discovery/facets') {
      body = { api_version: 'v2', dimensions: {}, meta: { ...releaseMeta, filters: { country_code: null, region: null, category: null, source_type: null, display_precision: null, lifecycle_status: null } } };
    } else if (path === `/api/v2/locations/${facilityId}`) {
      body = { api_version: 'v2', data: row, meta: releaseMeta };
    } else if (path === '/api/v2/map/feed') {
      body = { api_version: 'v2', data: { type: 'FeatureCollection', features: [{ type: 'Feature', id: facilityId, geometry: { type: 'Point', coordinates: [row.longitude, row.latitude] }, properties: { facility_id: facilityId, source_id: row.provenance_source_id, category_key: row.taxonomy_display_category, category_keys: row.taxonomy_primary_categories, precision: row.display_precision, weight: 1, country_code: row.country_code } }] }, meta: { profile: 'official', release_id: releaseId, manifest_sha256: 'a'.repeat(64), suppression_generation: 1, feature_count: 1, public_record_count: 1, unmapped_count: 0, release_label: 'Synthetic release', dataset_version: 'synthetic' } };
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
}

async function setSpanishAndTheme(page: Page, theme: 'Claro' | 'Oscuro') {
  const tools = page.getByRole('button', { name: 'Herramientas', exact: true });
  if (await tools.getAttribute('aria-expanded') !== 'true') await tools.click();
  await page.getByLabel('Idioma', { exact: true }).selectOption('es');
  const toggle = page.locator('.masthead .theme-toggle');
  const selectedLight = theme === 'Claro';
  if ((await toggle.getAttribute('aria-pressed')) !== String(selectedLight)) await toggle.click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'es');
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme === 'Claro' ? 'light' : 'dark');
}

test('Spanish map controls stay usable in Tools at 320px, 375px and 390px in either theme', async ({ page }, testInfo) => {
  await mockSanitizedApi(page);
  await page.addInitScript(() => localStorage.setItem('uec-language', 'es'));
  await page.goto('./#/map');
  await expect(page.getByRole('button', { name: 'Buscar en el mapa' })).toBeVisible();
  await page.getByRole('button', { name: 'Herramientas', exact: true }).click();

  for (const width of [390, 375, 320]) {
    await page.setViewportSize({ width, height: 844 });
    for (const theme of ['Claro', 'Oscuro'] as const) {
      await setSpanishAndTheme(page, theme);
      const geometry = await page.evaluate(() => {
        const toolbar = document.querySelector('.map-view-tools')!.getBoundingClientRect();
        const hint = document.querySelector('.gesture-hint')!;
        const toolbarSurface = document.querySelector('.map-view-tools')!;
        const style = getComputedStyle(hint);
        return {
          overflow: toolbarSurface.scrollWidth > toolbarSurface.clientWidth,
          hintDisplay: style.display,
          touchTargets: [...document.querySelectorAll('.map-view-tools select, .map-view-tools button')].map(control => control.getBoundingClientRect().height),
          touchHelpVisibleToAssistiveTech: document.querySelector('#map-camera-help')?.textContent?.trim(),
          labelClipped: toolbar.scrollWidth > toolbar.clientWidth,
        };
      });
      expect(geometry.overflow, `${width}px ${theme}: map controls overflow their Tools group`).toBe(false);
      expect(geometry.labelClipped, `${width}px ${theme}: Tools controls overflow their group`).toBe(false);
      expect(geometry.hintDisplay, `${width}px ${theme}: gesture hint remains visible in Tools`).not.toBe('none');
      expect(geometry.touchTargets.every(height => height >= 44), `${width}px ${theme}: map controls keep 44px touch targets`).toBe(true);
      expect(geometry.touchHelpVisibleToAssistiveTech, `${width}px ${theme}: camera and touch help remains available`).toContain('dos dedos');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}px ${theme}: page overflow`).toBe(true);

      await page.screenshot({ path: testInfo.outputPath(`spanish-map-${width}-${theme.toLowerCase()}.png`) });
      if (width === 390) {
        await expect(page.getByLabel('Idioma', { exact: true })).toHaveValue('es');
        await expect(page.locator('#shared-tools-menu').getByRole('button', { name: /Tema (claro|oscuro)/ })).toHaveCount(0);
        await expect(page.locator('.masthead .theme-toggle')).toHaveAttribute('aria-pressed', String(theme === 'Claro'));
        await page.screenshot({ path: testInfo.outputPath(`spanish-tools-390-${theme.toLowerCase()}.png`) });
        await page.screenshot({ path: testInfo.outputPath(`map-es-mobile-${theme.toLowerCase()}-tools-open.png`), fullPage: true });
        await page.getByRole('button', { name: 'Cerrar herramientas', exact: true }).click();
        await expect(page.locator('.map-view-tools')).toHaveCount(0);
        await expect(page.getByRole('button', { name: 'Buscar en el mapa' })).toBeVisible();
        await page.screenshot({ path: testInfo.outputPath(`map-es-mobile-${theme.toLowerCase()}-tools-closed.png`), fullPage: true });
        await page.getByRole('button', { name: 'Herramientas', exact: true }).click();
        await page.setViewportSize({ width, height: 844 });
      }
    }
  }
});
