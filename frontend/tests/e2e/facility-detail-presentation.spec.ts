import { expect, test, type Page } from '@playwright/test';

// Entirely synthetic public projections; no source rows are retained here.
const id = '550e8400-e29b-41d4-a716-446655440000';
const release = 'synthetic-detail-release';
const observed = '2026-01-01T00:00:00Z';
const row = {
  facility_id: id, canonical_name: 'Synthetic processing facility', city: 'Synthetic locality', country_code: 'DK',
  category: 'processing_and_preparation', source_type: 'official', publication_profile: 'official',
  factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved', reviewer_role: null,
  publication_warning: null, display_precision: 'source_reported', latitude: 55, longitude: 10,
  first_observed_at: null, last_observed_at: observed, observation_count: 1, lifecycle_status: 'active_observed',
  provenance_source_id: 'synthetic-source', provenance_source: null, provenance_source_name: 'Synthetic source',
  provenance_source_url: 'https://example.test/source', provenance_retrieved_at: observed, source_rights_status: 'cleared',
  release_id: release, release_ruleset_version: 'synthetic-rules', taxonomy_display_category: 'processing_and_preparation',
  taxonomy_primary_categories: ['processing_and_preparation'],
  taxonomy_leaf_activities: [{ key: 'nrte_chicken_processing', label: 'nrte_chicken_processing' }, { key: 'cutting', label: 'Meat cutting' }, { key: 'processing', label: 'Processing' }],
  taxonomy_assignments: [{ primary_key: 'processing_and_preparation', leaf_key: 'nrte_chicken_processing',
    leaf_label: 'nrte_chicken_processing', source_label: 'Native poultry activity', source_code: 'poultry_activity',
    method: 'direct', status: 'mapped', taxonomy_version: 'synthetic-taxonomy-version' }],
};
const facts = {
  alternate_names: ['Synthetic former name'], species_slaughtered: { poultry: true },
  processing_activities: { nrte_chicken_processing: true, meat_cutting: 'Yes', separate_activity: 'No' },
  establishment_number: 'SYNTHETIC-1',
  derived_source_volume_ranges: [{ ordinal_code: 'A', lower: null, upper: 1000,
    bounds: 'exclusive_upper', unit: 'head', period: 'trailing_360_days',
    method_version: 'fsis-mpi-volume-codebook-2026-03-24-v1', source_codebook_url: 'https://example.test/codebook',
    verification_state: 'source_codebook_verified' }, { ordinal_code: '2', lower: 10000, upper: 100000,
    bounds: 'inclusive_lower_exclusive_upper', unit: 'pounds', period: 'month',
    method_version: 'fsis-mpi-volume-codebook-2026-03-24-v1', source_codebook_url: 'https://example.test/codebook',
    verification_state: 'source_codebook_verified' }],
};
const meta = { release_id: release, ruleset_version: 'synthetic-rules', profile: 'official', release_created_at: observed };

async function mockPublicRecord(page: Page, overrides: Record<string, unknown> = {}, options: { failFirstReport?: boolean } = {}) {
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  await page.route('https://server.arcgisonline.com/**', route => route.abort());
  let reportFailureRemaining = options.failFirstReport ? 1 : 0;
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith('/api/')) return route.fallback();
    let body: unknown;
    if (path === '/api/v2/releases/manifest') body = { api_version: 'v2', data: { release_id: release, profile: 'official', manifest: {}, manifest_sha256: 'a'.repeat(64), suppression_generation: 1 } };
    else if (path === `/api/v2/locations/${id}`) body = { api_version: 'v2', data: { ...row, ...facts, ...overrides }, meta };
    else if (path === '/api/v2/locations') body = { api_version: 'v2', data: [{ ...row, ...overrides }], meta: { ...meta, coverage_note: 'Synthetic test coverage.', total_count: 1, next_cursor: null } };
    else if (path === `/api/v2/locations/${id}/aphis-report-links`) {
      if (reportFailureRemaining > 0) { reportFailureRemaining -= 1; return route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }); }
      const kind = new URL(route.request().url()).searchParams.get('kind');
      body = { api_version: 'v2', data: kind === 'annual_reports' ? [{
        reference_id: '550e8400-e29b-41d4-a716-446655440001', source_id: 'us.aphis.annual-reports', evidence_type: 'annual_reports',
        event_date: null, event_period: '2025',
        source_url: 'https://direct.aphis.usda.gov/awa/research-facility-report/annual-summary',
        report_url: 'https://www.aphis.usda.gov/sites/default/files/annual-report.pdf', column_e_url: null,
        reference_origin: 'release_approved_evidence', match_method: 'exact_source_identifier',
      }] : [], meta: { profile: 'official', release_id: release, ruleset_version: 'synthetic-rules', kind, limit: 20, next_cursor: null, public_projection: true } };
    }
    else if (path.startsWith('/api/v2/graph/')) body = { api_version: 'v2-graph-v1', data: [], meta: { ...meta, limit: 20, page_max: 100, next_cursor: null, public_projection: true } };
    else if (path === '/api/v2/map/feed') body = { api_version: 'v2', data: { type: 'FeatureCollection', features: [] }, meta: {
      profile: 'official', release_id: release, manifest_sha256: 'a'.repeat(64), suppression_generation: 1,
      feature_count: 0, public_record_count: 1, unmapped_count: 0, release_label: 'Synthetic release', dataset_version: 'synthetic',
    } };
    else return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
}

test('map detail shows one category and each activity, preserves facts, and opens its release-pinned facility page', async ({ page }) => {
  let reportRequests = 0;
  page.on('request', request => { if (request.url().includes(`/api/v2/locations/${id}/aphis-report-links`)) reportRequests += 1; });
  await mockPublicRecord(page, { latitude: 55.123456789, longitude: 10.123456789, geometry_provenance: { origin: 'source_coordinates', method: 'source_method_unknown' } });
  await page.goto(`./#/map?selected=${id}&release_id=${release}`);
  const panel = page.locator('.reading-sheet[aria-label="Record evidence"]');
  await expect(panel.locator('.detail h1')).toContainText(row.canonical_name);
  const drawerOrder = await panel.locator('.detail').evaluate(root => {
    const location = root.querySelector('#location-heading');
    const activities = root.querySelector('#taxonomy-heading');
    return Boolean(location && activities && (activities.compareDocumentPosition(location) & Node.DOCUMENT_POSITION_FOLLOWING));
  });
  expect(drawerOrder).toBe(true);
  await expect(panel.getByText('Processing and preparation', { exact: true })).toHaveCount(1);
  const overview = panel.locator('.classification-summary .summary');
  await expect(overview).toContainText('Meat cutting');
  await expect(overview).toContainText('NRTE chicken processing');
  await expect(overview).not.toContainText('Separate activity');
  await panel.locator('.classification-summary summary').click();
  await expect(panel).not.toContainText(/synthetic-taxonomy-version|Taxonomy version|Primary categories|Classification provenance|not independently|Source confirmed/);
  await expect(panel.getByText('Source-provided coordinates', { exact: true })).toBeVisible();
  await expect(panel.getByText('55.123457, 10.123457', { exact: true })).toBeVisible();
  await expect(panel.getByText('Location method', { exact: true })).toHaveCount(0);
  await panel.locator('.source-facts-section > summary').click();
  await expect(panel.getByText('Synthetic former name', { exact: true })).toBeVisible();
  await expect(panel.getByText('SYNTHETIC-1', { exact: true })).toBeVisible();
  await expect(panel.getByText('10,000 to less than 100,000 pounds/month', { exact: true })).toBeVisible();
  await expect(panel.locator('.classification-summary details')).toContainText('Native poultry activity');
  await expect(panel.locator('.classification-summary details')).toContainText('poultry_activity');
  await expect(panel).not.toContainText(/Direct|Mapped|synthetic-taxonomy-version/);
  await expect(panel.getByRole('heading', { name: 'APHIS reports' })).toHaveCount(0);
  expect(reportRequests).toBe(0);
  const link = panel.getByRole('link', { name: 'Open facility page', exact: true });
  await expect(link).toHaveAttribute('href', `#/records/${id}?profile=official&release_id=${release}`);
  await expect(panel.getByRole('button', { name: 'Copy facility link' })).toBeVisible();
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await panel.getByRole('button', { name: 'Copy facility link' }).click();
  await expect(panel.locator('.detail h1 [role="status"]')).toHaveText('Link copied');
  const copiedRailLink = await page.evaluate(() => navigator.clipboard.readText());
  expect(new URL(copiedRailLink).hash).toBe(`#/records/${id}?profile=official&release_id=${release}`);
  await page.setViewportSize({ width: 390, height: 844 });
  await link.click();
  await expect(page.locator('.public-record h1')).toHaveText(row.canonical_name);
  await expect(page.locator('.location-preview')).toHaveAttribute('aria-label', 'Satellite location preview');
  const pageOrder = await page.locator('.public-record').evaluate(root => {
    const location = root.querySelector('#location-heading');
    const preview = root.querySelector('.location-preview');
    const activities = root.querySelector('#activities-heading');
    return Boolean(location && preview && activities &&
      (activities.compareDocumentPosition(location) & Node.DOCUMENT_POSITION_FOLLOWING) &&
      (location.compareDocumentPosition(preview) & Node.DOCUMENT_POSITION_FOLLOWING));
  });
  expect(pageOrder).toBe(true);
  await expect(page.locator('.location-preview .map')).toHaveAttribute('data-pin-loaded', 'true');
  await expect(page.locator('.public-record')).toContainText('Less than 1,000 animals');
  await expect(page.getByRole('button', { name: 'Copy facility link' })).toBeVisible();
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  const copyButton = page.locator('.public-record h1 .share');
  const layout = () => page.evaluate(() => {
    const heading = document.querySelector('.public-record h1')!.getBoundingClientRect();
    const button = document.querySelector('.public-record h1 .share')!.getBoundingClientRect();
    return { heading: [heading.x, heading.y, heading.width, heading.height], button: [button.x, button.y, button.width, button.height] };
  });
  const initialLayout = await layout();
  const originalIcon = await copyButton.locator('svg path').getAttribute('d');
  await copyButton.click();
  await expect(page.locator('.public-record h1 [role="status"]')).toHaveText('Link copied');
  expect(await layout()).toEqual(initialLayout);
  await expect.poll(() => copyButton.locator('svg path').getAttribute('d'), { timeout: 5000 }).toBe(originalIcon);
  expect(await layout()).toEqual(initialLayout);
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => { throw new Error('synthetic clipboard rejection'); } }, configurable: true }));
  await copyButton.click();
  await expect(page.locator('.public-record h1 [role="status"]')).toHaveText('Could not copy facility link');
  expect(await layout()).toEqual(initialLayout);
  await expect.poll(() => copyButton.locator('svg path').getAttribute('d'), { timeout: 5000 }).toBe(originalIcon);
  expect(await layout()).toEqual(initialLayout);
  await expect(page.locator('.public-record').getByText('Processing and preparation', { exact: true })).toHaveCount(1);
  await expect(page.locator('.public-record')).not.toContainText(/synthetic-taxonomy-version|not independently/);
  await expect(page.getByRole('link', { name: 'Open facility page', exact: true })).toHaveCount(0);
});

test('Spanish processing summary is deduplicated in map detail and the full record', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('uec-language', 'es'));
  await mockPublicRecord(page);
  await page.goto(`./#/map?selected=${id}&release_id=${release}`);
  const panel = page.locator('.reading-sheet[aria-label="Record evidence"]');
  await expect(panel.getByText('Procesamiento y preparación', { exact: true })).toHaveCount(1);
  const mapActivities = panel.locator('.classification-summary .summary');
  await expect(mapActivities).toContainText('Procesamiento de pollo (NRTE)');
  await expect(mapActivities).toContainText('Meat cutting');
  await expect(mapActivities).not.toHaveText(/(?:^|,\s*)Procesamiento(?:,\s*|$)/);
  await expect(panel.getByRole('link', { name: 'Abrir página de la instalación', exact: true })).toBeVisible();
  await panel.locator(`a[href="#/records/${id}?profile=official&release_id=${release}"]`).click();
  const full = page.locator('.public-record');
  await expect(full.getByText('Procesamiento y preparación', { exact: true })).toHaveCount(1);
  const fullActivities = full.locator('.classification-summary .summary');
  await expect(fullActivities).toContainText('Procesamiento de pollo (NRTE)');
  await expect(fullActivities).toContainText('Meat cutting');
  await expect(fullActivities).not.toHaveText(/(?:^|,\s*)Procesamiento(?:,\s*|$)/);
});

test('city-level geocoding keeps its approximation and actual provider score in one Location section', async ({ page }) => {
  await mockPublicRecord(page, { display_precision: 'provider_locality_approximate', geometry_provenance: {
    origin: 'provider_geocode', method: 'geoapify_forward', provider: 'Synthetic geocoder', confidence: '0.72', confidence_band: 'medium',
  } });
  await page.goto(`./#/map?selected=${id}&release_id=${release}`);
  const panel = page.locator('.reading-sheet[aria-label="Record evidence"]');
  await expect(panel.getByRole('heading', { name: 'Location', exact: true })).toHaveCount(1);
  await expect(panel).toContainText('Approximate location');
  await expect(panel).toContainText('Geoapify forward');
  await expect(panel).toContainText('Synthetic geocoder');
  await expect(panel).toContainText('0.72 (provider score) · Medium');
  await expect(panel.getByText('55, 10', { exact: true })).toBeVisible();
  await expect(panel.getByText('Address', { exact: true })).toHaveCount(0);
  await panel.getByRole('link', { name: 'Open facility page', exact: true }).click();
  const full = page.locator('.public-record');
  await expect(full).toContainText('Approximate location');
  await expect(full.locator('.location-preview')).toHaveAttribute('aria-label', 'Approximate road map preview');
  const pageOrder = await full.evaluate(root => {
    const location = root.querySelector('#location-heading');
    const preview = root.querySelector('.location-preview');
    const activities = root.querySelector('#activities-heading');
    return Boolean(location && preview && activities &&
      (activities.compareDocumentPosition(location) & Node.DOCUMENT_POSITION_FOLLOWING) &&
      (location.compareDocumentPosition(preview) & Node.DOCUMENT_POSITION_FOLLOWING));
  });
  expect(pageOrder).toBe(true);
  await expect(full.locator('.location-preview .map')).toHaveAttribute('data-pin-loaded', 'true');
  await expect(full).toContainText('0.72 (provider score) · Medium');
  await expect(full.getByRole('heading', { name: 'Location', exact: true })).toHaveCount(1);
});

test('mobile detail shares the middle-height sheet with the map and preserves scrolling and dismissal', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockPublicRecord(page);
  const open = async () => {
    await page.goto(`./#/map?selected=${id}&release_id=${release}`);
    await expect(page.locator('.reading-sheet .detail h1')).toHaveText(row.canonical_name);
  };
  await open();
  const workspace = page.locator('.workspace > .results');
  const panel = page.locator('.reading-sheet.dossier');
  const close = panel.getByRole('button', { name: 'Close record detail' });
  for (const [width, height] of [[375, 812], [375, 667], [320, 667]]) {
    await page.setViewportSize({ width: width!, height: height! });
    await expect(workspace).toHaveCSS('position', 'absolute');
    const workspaceBox = (await workspace.boundingBox())!;
    const headerBox = (await page.locator('.field-view > .masthead').boundingBox())!;
    expect(workspaceBox.x).toBe(0);
    expect(workspaceBox.width).toBe(width);
    expect(workspaceBox.y).toBeGreaterThan(headerBox.y + headerBox.height);
    const mapBox=(await page.locator('.map-stage').boundingBox())!;
    expect(mapBox.y).toBeCloseTo(headerBox.y+headerBox.height,0);
    expect(mapBox.y+mapBox.height).toBeCloseTo(height!,0);
    expect(workspaceBox.height).toBeCloseTo((height!-headerBox.height)*.48,0);
    expect(workspaceBox.y + workspaceBox.height).toBeCloseTo(height!, 0);
    const search = workspace.locator('#field-search');
    await expect(search).toBeHidden();
    await expect(workspace.locator('.search-tools')).toBeHidden();
    await expect(workspace.locator('.csv-download')).toBeHidden();
    await expect(workspace.locator('.result-status')).toBeHidden();
    const box = (await panel.boundingBox())!;
    expect(box.x).toBe(0);
    expect(box.width).toBe(width);
    expect(box.y).toBeCloseTo(workspaceBox.y+45, 0);
    expect(box.height).toBeGreaterThan(100);
    expect(box.y + box.height).toBeCloseTo(height!, 0);
    expect(await workspace.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  }
  await expect(close).toBeFocused();
  await panel.evaluate(element => element.scrollTop = element.scrollHeight);
  await expect(close).toBeInViewport();
  const scrolled = await panel.evaluate(element => ({ scrollTop: element.scrollTop, overflow: getComputedStyle(element).overflowY }));
  expect(scrolled.scrollTop).toBeGreaterThan(0);
  expect(scrolled.overflow).toBe('auto');
  const stickyHeader = panel.locator('.dossier-header');
  await expect(stickyHeader).toHaveCSS('position', 'sticky');
  expect((await stickyHeader.boundingBox())!.y).toBeCloseTo((await panel.boundingBox())!.y, 0);
  const copyLink = panel.getByRole('button', { name: 'Copy facility link' });
  await expect(copyLink).toBeVisible();
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await copyLink.click();
  const copiedLink = await page.evaluate(() => navigator.clipboard.readText());
  expect(new URL(copiedLink).hash).toBe(`#/records/${id}?profile=official&release_id=${release}`);
  await close.focus();
  await page.keyboard.press('Enter');
  await expect(panel).toHaveCount(0);
  await open();
  await page.keyboard.press('Escape');
  await expect(panel).toHaveCount(0);
});

test('mobile diagnostics temporarily cover an expanded selected sheet and restore its context on close', async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await mockPublicRecord(page);
  await page.goto(`./#/map?selected=${id}&release_id=${release}`);
  await expect(page.locator('.dossier h1')).toHaveText(row.canonical_name);
  const handle=page.getByRole('button',{name:'View facility details',exact:true});
  await handle.focus();await page.keyboard.press('End');
  await page.getByRole('button',{name:'Tools',exact:true}).click();
  await page.getByLabel('Enable debug menu',{exact:true}).check();
  await page.getByRole('button',{name:'Close Tools',exact:true}).click();
  await page.getByRole('button',{name:'Debug menu',exact:true}).click();
  const debug=page.getByRole('complementary',{name:'Debug menu',exact:true});
  await expect(debug).toBeVisible();
  expect((await debug.boundingBox())!.height).toBeGreaterThan(300);
  await expect(page.locator('.results')).toHaveAttribute('inert','');
  await debug.locator('#debug-sheet-height').press('End');
  await expect(debug.locator('#debug-sheet-height')).toHaveValue('65');
  await debug.getByRole('button',{name:'Close debug menu',exact:true}).click();
  await expect(handle).toBeVisible();
  await expect(handle).toHaveAttribute('data-sheet-state','expanded');
  await expect(page.locator('.results')).not.toHaveAttribute('inert','');
  expect(new URL(page.url()).hash).toContain(`selected=${id}`);
});

test('unmapped public records do not create a location map', async ({ page }) => {
  await mockPublicRecord(page, { display_precision: 'unmapped', latitude: null, longitude: null });
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  await expect(page.getByRole('heading', { name: row.canonical_name })).toBeVisible();
  await expect(page.locator('.location-preview')).toHaveCount(0);
});

test('map detail keeps long-name copy beside its heading, classification above facts, and the facility link at the bottom', async ({ page }) => {
  await page.setViewportSize({width:320,height:740});
  await mockPublicRecord(page,{canonical_name:'Synthetic exceptionally long processing and cold storage facility record for the narrow mobile layout'});
  await page.goto(`./#/map?selected=${id}&release_id=${release}`);
  const detail=page.locator('.dossier .detail');
  await expect(detail.locator('.classification-disclosure details')).not.toHaveAttribute('open','');
  const layout=await detail.evaluate(root=>{
    const heading=root.querySelector('h1')!.getBoundingClientRect(),copy=root.querySelector('h1 .share')!.getBoundingClientRect();
    const classification=root.querySelector('.classification-disclosure')!,facts=root.querySelector('.source-facts-section')!,link=root.querySelector('.open-facility')!,review=root.querySelector('.evidence-section')!;
    return {copyY:copy.y,headingY:heading.y,copyRight:copy.right,headingRight:heading.right,classificationBeforeFacts:Boolean(classification.compareDocumentPosition(facts)&Node.DOCUMENT_POSITION_FOLLOWING),linkAfterReview:Boolean(review.compareDocumentPosition(link)&Node.DOCUMENT_POSITION_FOLLOWING)};
  });
  expect(layout.copyY).toBeCloseTo(layout.headingY,0);
  expect(layout.copyRight).toBeLessThanOrEqual(layout.headingRight);
  expect(layout.classificationBeforeFacts).toBe(true);
  expect(layout.linkAfterReview).toBe(true);
  await expect(detail.locator('.open-facility')).toHaveAttribute('href',`#/records/${id}?profile=official&release_id=${release}`);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});

for(const state of ['empty','populated','error'] as const) test(`map connection disclosure defaults correctly for ${state} data`,async({page})=>{
  await mockPublicRecord(page);
  await page.route('**/api/v2/graph/**',route=>{
    if(state==='error')return route.fulfill({status:503,json:{}});
    const endpoint=(entity_type:string,entity_id:string,display_name:string)=>({entity_type,entity_id,display_name,source_id:'synthetic-source',identifier_type:'synthetic',source_identifier:entity_id});
    const edge={connection_edge_id:'550e8400-e29b-41d4-a716-446655440009',from:endpoint('facility',id,'Synthetic facility'),to:endpoint('organization','550e8400-e29b-41d4-a716-446655440008','Synthetic research organization'),relationship_type:'source_assertion',connection_type:'exact',confidence:1,confidence_band:'exact',match_method:'exact_source_identifier',signals:{},contradictions:[],provenance:{source_ids:['synthetic-source'],observed_at:observed,release_id:release},source_references:[{source_id:'synthetic-source'}],observed_at:observed,computed_at:observed,ruleset:'synthetic-rules',conflicting:false,publication_warning:'Synthetic connection fixture',disclaimer:'Synthetic evidence only'};
    return route.fulfill({json:{api_version:'v2-graph-v1',data:state==='populated'?[edge]:[],meta:{...meta,limit:20,page_max:100,next_cursor:null,public_projection:true}}});
  });
  await page.goto(`./#/map?selected=${id}&release_id=${release}`);
  const disclosure=page.locator('.connections-disclosure');
  if(state==='empty'){await expect(disclosure.locator('.empty')).toHaveText('None');await expect(disclosure).not.toHaveAttribute('open','');await disclosure.locator(':scope > summary').click();await expect(disclosure.getByText('None',{exact:true})).toBeVisible()}
  else if(state==='populated'){await expect(disclosure.getByText('Synthetic research organization',{exact:true})).toBeVisible();await expect(disclosure).toHaveAttribute('open','');await expect(disclosure).toContainText('Exact source')}
  else{await expect(disclosure.getByRole('alert')).toBeVisible();await expect(disclosure.getByRole('button',{name:'Retry',exact:true})).toBeVisible()}
});

test('a failed map image leaves the facility record readable and announces the map limitation', async ({ page }) => {
  await page.route('**/v1-pins/**', route => route.abort());
  await mockPublicRecord(page);
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  await expect(page.locator('.location-preview')).toBeVisible();
  await expect(page.locator('.location-preview [role="status"]')).toHaveText('Location map unavailable.');
  await expect(page.locator('.public-record').getByRole('heading', { name: 'Activities and classification' })).toBeVisible();
});

test('APHIS source records load report links only after a report type is selected', async ({ page }) => {
  let reportRequests = 0;
  page.on('request', request => { if (request.url().includes(`/api/v2/locations/${id}/aphis-report-links`)) reportRequests += 1; });
  await mockPublicRecord(page, { provenance_source_id: 'us.aphis' }, { failFirstReport: true });
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  await expect(page.getByRole('heading', { name: 'APHIS reports' })).toBeVisible();
  expect(reportRequests).toBe(0);
  await page.getByRole('button', { name: 'Annual reports' }).click();
  await expect(page.getByRole('alert')).toContainText('Reports could not be loaded.');
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.getByText('Annual report · FY2025', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open report', exact: true })).toBeVisible();
  expect(reportRequests).toBe(2);
});
