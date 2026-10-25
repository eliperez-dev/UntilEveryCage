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

const contrastRatio = (foreground: string, background: string) => {
  const luminance = (color: string) => {
    const channels = color.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [];
    const linear = channels.map(value => {
      const channel = value / 255;
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * linear[0]! + 0.7152 * linear[1]! + 0.0722 * linear[2]!;
  };
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((left, right) => right - left);
  return (lighter + 0.05) / (darker! + 0.05);
};

async function setSpanishAndTheme(page: Page, theme: 'Claro' | 'Oscuro') {
  const tools = page.getByRole('button', { name: 'Herramientas', exact: true });
  if (await tools.getAttribute('aria-expanded') !== 'true') await tools.click();
  await page.getByLabel('Idioma', { exact: true }).selectOption('es');
  await page.getByRole('button', { name: theme, exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'es');
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme === 'Claro' ? 'light' : 'dark');
  await page.getByRole('button', { name: 'Cerrar herramientas', exact: true }).click();
  await expect(page.locator('.map-controls')).toBeVisible();
}

test('Spanish map controls do not overlap at 390px or 375px in either theme', async ({ page }, testInfo) => {
  await mockSanitizedApi(page);
  await page.addInitScript(() => localStorage.setItem('uec-language', 'es'));
  await page.goto('./#/map');
  await expect(page.getByRole('button', { name: 'Buscar en el mapa' })).toBeVisible();
  await expect(page.locator('.map-controls')).toBeVisible();

  for (const width of [390, 375]) {
    await page.setViewportSize({ width, height: 844 });
    for (const theme of ['Claro', 'Oscuro'] as const) {
      await setSpanishAndTheme(page, theme);
      const geometry = await page.evaluate(() => {
        const search = document.querySelector('.search-toggle')!.getBoundingClientRect();
        const toolbar = document.querySelector('.map-controls-wrap')!.getBoundingClientRect();
        const hint = document.querySelector('.gesture-hint')!;
        const toolbarSurface = document.querySelector('.map-controls')!;
        const style = getComputedStyle(hint);
        const background = getComputedStyle(toolbarSurface).backgroundColor;
        return {
          overlaps: search.left < toolbar.right && toolbar.left < search.right && search.top < toolbar.bottom && toolbar.top < search.bottom,
          overflow: toolbarSurface.scrollWidth > toolbarSurface.clientWidth,
          hintColor: style.color,
          hintFontSize: parseFloat(style.fontSize),
          toolbarBackground: background,
          labelClipped: (() => {
            const label = document.querySelector('.map-controls-label')!;
            const labelBox = label.getBoundingClientRect();
            const toolbarBox = toolbarSurface.getBoundingClientRect();
            return labelBox.left < toolbarBox.left || labelBox.right > toolbarBox.right;
          })(),
        };
      });
      expect(geometry.overlaps, `${width}px ${theme}: search and map controls overlap`).toBe(false);
      expect(geometry.overflow, `${width}px ${theme}: map controls overflow their toolbar`).toBe(false);
      expect(geometry.labelClipped, `${width}px ${theme}: translated toolbar label is clipped`).toBe(false);
      expect(geometry.hintFontSize, `${width}px ${theme}: hint size`).toBeGreaterThanOrEqual(10);
      expect(contrastRatio(geometry.hintColor, geometry.toolbarBackground), `${width}px ${theme}: hint contrast`).toBeGreaterThanOrEqual(4.5);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}px ${theme}: page overflow`).toBe(true);

      await page.screenshot({ path: testInfo.outputPath(`spanish-map-${width}-${theme.toLowerCase()}.png`) });
      if (width === 390) {
        const tools = page.getByRole('button', { name: 'Herramientas', exact: true });
        await tools.click();
        await expect(page.getByLabel('Idioma', { exact: true })).toHaveValue('es');
        await expect(page.getByRole('group', { name: 'Tema de color' })).toBeVisible();
        await expect(page.getByRole('button', { name: theme, exact: true })).toHaveAttribute('aria-pressed', 'true');
        await page.screenshot({ path: testInfo.outputPath(`spanish-tools-390-${theme.toLowerCase()}.png`) });
        await page.getByRole('button', { name: 'Cerrar herramientas', exact: true }).click();
      }
    }
  }
});
