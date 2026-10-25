import { expect, test, type Page } from '@playwright/test';

const id = '550e8400-e29b-41d4-a716-446655440000';
const release = 'synthetic-theme-release';
const observed = '2026-01-01T00:00:00Z';
const row = {
  facility_id: id, canonical_name: 'Synthetic theme facility', city: 'Synthetic locality', country_code: 'DK',
  category: 'processing_and_preparation', source_type: 'official', publication_profile: 'official',
  factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved', reviewer_role: null,
  publication_warning: null, display_precision: 'source_reported', latitude: 55, longitude: 10,
  first_observed_at: null, last_observed_at: observed, observation_count: 1, lifecycle_status: 'active_observed',
  provenance_source_id: 'synthetic-theme-source', provenance_source: null, provenance_source_name: 'Synthetic source',
  provenance_source_url: 'https://example.test/source', provenance_retrieved_at: observed, source_rights_status: 'cleared',
  release_id: release, release_ruleset_version: 'synthetic-rules', taxonomy_display_category: 'processing_and_preparation',
  taxonomy_primary_categories: ['processing_and_preparation'],
  aphis_annual_reports: [{ fiscal_year: '2025', species_counts: [{ species: 'dogs', count: 1 }],
    source_url: 'https://direct.aphis.usda.gov/awa/research-facility-report/annual-summary',
    safe_provenance: { source_id: 'us.aphis.annual-reports', evidence_type: 'annual_reports', match_method: 'exact_source_identifier', matched_identifier_types: ['certificate_number'] } }],
};
const meta = { release_id: release, ruleset_version: 'synthetic-rules', profile: 'official', release_created_at: observed };

async function mockSanitizedApi(page: Page) {
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  await page.route('https://server.arcgisonline.com/**', route => route.abort());
  await page.route('**/health/live', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ status: 'ok', service: 'uec-api', application_version: '2.0.0' }),
  }));
  await page.route('**/api/**', async route => {
    const requestUrl = new URL(route.request().url());
    const path = requestUrl.pathname;
    if (!path.startsWith('/api/')) return route.fallback();
    let body: unknown = {};
    if (path === '/api/v2/releases/manifest') {
      body = { api_version: 'v2', data: { release_id: release, profile: requestUrl.searchParams.get('profile') ?? 'official', manifest: {}, manifest_sha256: 'a'.repeat(64), suppression_generation: 1 } };
    } else if (path === `/api/v2/locations/${id}`) {
      body = { api_version: 'v2', data: row, meta };
    } else if (path === `/api/v2/locations/${id}/aphis-report-links`) {
      const kind = requestUrl.searchParams.get('kind');
      body = { api_version: 'v2', data: kind === 'annual_reports' ? [{
        reference_id: '550e8400-e29b-41d4-a716-446655440001', source_id: 'us.aphis.annual-reports', evidence_type: 'annual_reports',
        event_date: null, event_period: '2025', source_url: 'https://direct.aphis.usda.gov/awa/research-facility-report/annual-summary',
        report_url: 'https://www.aphis.usda.gov/sites/default/files/synthetic-annual-report.pdf',
        column_e_url: 'https://www.aphis.usda.gov/sites/default/files/synthetic-column-e.pdf',
        reference_origin: 'release_approved_evidence', match_method: 'exact_source_identifier',
      }] : [], meta: { profile: 'official', release_id: release, ruleset_version: meta.ruleset_version, kind, limit: 20, next_cursor: null, public_projection: true } };
    } else if (path === '/api/v2/locations') {
      body = { api_version: 'v2', data: [row], meta: { ...meta, total_count: 1, next_cursor: null, coverage_note: 'Synthetic fixture only.' } };
    } else if (path === '/api/v2/discovery/facets') {
      body = { api_version: 'v2', dimensions: {}, meta: { ...meta, coverage_scope: 'synthetic fixture', count_semantics: 'Synthetic test rows only.', filters: { country_code: null, region: null, category: null, source_type: null, display_precision: null, lifecycle_status: null } } };
    } else if (path === '/api/v2/map/feed') {
      body = { api_version: 'v2', data: { type: 'FeatureCollection', features: [{ type: 'Feature', id, geometry: { type: 'Point', coordinates: [row.longitude, row.latitude] }, properties: { facility_id: id, source_id: row.provenance_source_id, category_key: row.taxonomy_display_category, category_keys: row.taxonomy_primary_categories, precision: row.display_precision, weight: 1, country_code: row.country_code } }] }, meta: { profile: 'official', release_id: release, manifest_sha256: 'a'.repeat(64), suppression_generation: 1, feature_count: 1, public_record_count: 1, unmapped_count: 0, release_label: 'Synthetic release', dataset_version: 'synthetic' } };
    } else if (path.startsWith('/api/v2/graph/')) {
      body = { api_version: 'v2-graph-v1', data: [], meta: { ...meta, limit: 20, page_max: 100, next_cursor: null, public_projection: true } };
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
}

async function selectTheme(page: Page, theme: 'dark' | 'light') {
  const tools = page.getByRole('button', { name: 'Tools', exact: true });
  if (await tools.getAttribute('aria-expanded') !== 'true') await tools.click();
  const label = theme === 'light' ? 'Light' : 'Dark';
  const button = page.getByRole('group', { name: 'Color theme' }).getByRole('button', { name: label, exact: true });
  await button.click();
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
  await page.getByRole('button', { name: 'Close Tools', exact: true }).click();
}

const contrast = (foreground: string, background: string) => {
  const luminance = (color: string) => {
    const channels = color.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [];
    const linear = channels.map(value => {
      const component = value / 255;
      return component <= 0.04045 ? component / 12.92 : ((component + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * linear[0]! + 0.7152 * linear[1]! + 0.0722 * linear[2]!;
  };
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (light + 0.05) / (dark! + 0.05);
};

async function expectAppSurface(page: Page, selector: string, label: string, pageErrors: string[]) {
  try {
    await expect(page.locator(selector).first(), `${label} surface`).toBeVisible();
  } catch (error) {
    const body = await page.locator('body').innerText().catch(() => '<body text unavailable>');
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`${message}\nVisible body text:\n${body.slice(0, 3000)}\nPage errors:\n${pageErrors.join('\n') || '<none>'}`);
  }
}

test('the real theme control reflects translated selection, persists on reload, and survives denied storage', async ({ page }) => {
  await page.goto('./tests/fixtures/theme-control.html');
  const group = page.getByRole('group', { name: 'Tema de color' });
  const light = group.getByRole('button', { name: 'Claro' });
  const dark = group.getByRole('button', { name: 'Oscuro' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(dark).toHaveAttribute('aria-pressed', 'true');
  await expect(light).toHaveAttribute('aria-pressed', 'false');
  await light.click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(light).toHaveAttribute('aria-pressed', 'true');
  const controlStyle = await light.evaluate(button => ({ color: getComputedStyle(button).color, background: getComputedStyle(button).backgroundColor }));
  expect(contrast(controlStyle.color, controlStyle.background), 'translated light theme control contrast').toBeGreaterThanOrEqual(4.5);
  expect(await page.evaluate(() => localStorage.getItem('uec-theme'))).toBe('light');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.getByRole('button', { name: 'Claro' })).toHaveAttribute('aria-pressed', 'true');

  await page.addInitScript(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (key === 'uec-theme') throw new DOMException('Storage denied', 'SecurityError');
      return original.call(this, key, value);
    };
  });
  await page.evaluate(() => localStorage.removeItem('uec-theme'));
  await page.reload();
  await page.getByRole('button', { name: 'Claro' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.getByRole('button', { name: 'Claro' })).toHaveAttribute('aria-pressed', 'true');
});

test('saved theme is applied before the app module starts', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('uec-theme', 'light'));
  let resumeModule!: () => void;
  const hold = new Promise<void>(resolve => resumeModule = resolve);
  await page.route('**/src/main.ts*', async route => { await hold; await route.continue(); });
  await page.goto('./#/about', { waitUntil: 'commit' });
  await expect.poll(() => page.locator('html').getAttribute('data-theme')).toBe('light');
  expect(await page.evaluate(() => document.documentElement.style.colorScheme)).toBe('light');
  resumeModule();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty' })).toBeVisible();
});

const viewports = [{ name: 'desktop', width: 1280, height: 900 }, { name: 'mobile', width: 390, height: 844 }] as const;
const publicViews = [
  { route: `./#/map?release_id=${release}`, surface: '.map-controls', label: 'map controls' },
  { route: './#/database', surface: '.public-database', label: 'database' },
  { route: `./#/records/${id}?release_id=${release}`, surface: '.public-record', label: 'full facility detail' },
  { route: './#/contribute/bug', surface: '.bug-page', label: 'contribute form' },
  { route: './#/about', surface: '.about-page', label: 'About' },
  { route: './#/faq', surface: '.faq-page', label: 'FAQ' },
  { route: './#/database/api', surface: '.api-page', label: 'API' },
] as const;

for (const viewport of viewports) {
  for (const view of publicViews) {
    for (const theme of ['dark', 'light'] as const) {
      test(`${view.label} retains readable ${theme} surface on ${viewport.name}`, async ({ page }) => {
        const pageErrors: string[] = [];
        page.on('pageerror', error => pageErrors.push(error.stack ?? error.message));
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await mockSanitizedApi(page);
        await page.goto(view.route);
        await expectAppSurface(page, view.surface, view.label, pageErrors);
        if (view.label === 'map controls') {
          await page.getByRole('button', { name: 'Search map' }).click();
          const fixtureRecord = page.locator(`.record-list button[data-record-id="${id}"]`);
          await expect(fixtureRecord).toBeVisible();
          await fixtureRecord.click();
          await expect(page.locator('.reading-sheet[aria-label="Record evidence"] .detail')).toBeVisible();
          await expect(page.locator('.map-controls')).toBeVisible();
        }
        await selectTheme(page, theme);
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
        const style = await page.locator(view.surface).first().evaluate(element => {
          const own = getComputedStyle(element);
          let ancestor: Element | null = element;
          let background = 'rgba(0, 0, 0, 0)';
          while (ancestor && background === 'rgba(0, 0, 0, 0)') {
            background = getComputedStyle(ancestor).backgroundColor;
            ancestor = ancestor.parentElement;
          }
          return { color: own.color, background };
        });
        expect(style.color).not.toBe('rgba(0, 0, 0, 0)');
        expect(contrast(style.color, style.background), `${view.label} ${theme} contrast`).toBeGreaterThanOrEqual(4.5);
        if (view.label === 'map controls') {
          const detail = page.locator('.reading-sheet[aria-label="Record evidence"] .detail');
          await expect(detail).toBeVisible();
          const detailStyle = await detail.evaluate(element => {
            const computed = getComputedStyle(element);
            return { color: computed.color, background: getComputedStyle(element.parentElement!).backgroundColor };
          });
          expect(contrast(detailStyle.color, detailStyle.background), `selected map dossier ${theme} contrast`).toBeGreaterThanOrEqual(4.5);
        }
        if (view.label === 'API') {
          const operation = page.locator('.explorer .swagger-ui .opblock').first();
          await expect(operation).toBeVisible();
          const operationStyle = await operation.evaluate(element => {
            const computed = getComputedStyle(element);
            return { color: computed.color, background: computed.backgroundColor };
          });
          expect(contrast(operationStyle.color, operationStyle.background), `Swagger operation ${theme} contrast`).toBeGreaterThanOrEqual(4.5);
        }
        if (view.label === 'full facility detail' && theme === 'light') {
          await page.getByRole('button', { name: 'Fetch annual reports', exact: true }).click();
          const reportLink = page.locator('.public-record .aphis-reports a').first();
          await expect(reportLink).toBeVisible();
          const reportLinkStyle = await reportLink.evaluate(element => {
            let ancestor: Element | null = element;
            let background = 'rgba(0, 0, 0, 0)';
            while (ancestor && background === 'rgba(0, 0, 0, 0)') {
              background = getComputedStyle(ancestor).backgroundColor;
              ancestor = ancestor.parentElement;
            }
            return { color: getComputedStyle(element).color, background };
          });
          expect(contrast(reportLinkStyle.color, reportLinkStyle.background), 'light APHIS report link contrast').toBeGreaterThanOrEqual(4.5);
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${view.label} ${viewport.name} overflow`).toBe(true);
      });
    }
  }
}
