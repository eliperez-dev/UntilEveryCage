import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
const de: Record<string,string> = JSON.parse(readFileSync(new URL('../../src/app/locales/de.json', import.meta.url), 'utf8'));

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

for (const canonicalName of [null, 'Name not provided'] as const) test(`unmapped name presentation preserves source text (${canonicalName === null ? 'missing' : 'provided'})`, async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await page.addInitScript(() => localStorage.setItem('uec-language', 'de'));
  await mockPublicRecord(page, { canonical_name: canonicalName, display_precision: 'unmapped', latitude: null, longitude: null });
  await page.goto(`./#/map?release_id=${release}&list=open`);
  const name = canonicalName ?? de['Name not provided'];
  const result = page.locator(`[data-record-id="${id}"]`);
  await expect(result.locator('strong')).toHaveText(name);
  await expect(result).toContainText(de['Unmapped']);
  await result.click();
  const panel = page.locator('.map-summary');
  await expect(panel.locator('strong')).toHaveText(name);
  await expect(panel.getByRole('link', { name: de['Open in maps'], exact: true })).toHaveCount(0);
  await panel.getByRole('link', { name: de['View full record'], exact: true }).click();
  await expect(page.locator('.public-record > h1')).toContainText(name);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

for (const width of [1440, 375]) test(`direct evidence access and optional location mechanics work at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await mockPublicRecord(page, { city: width === 375 ? null : row.city, display_precision: 'approximate', geometry_provenance: {
    origin: 'provider_derived', method: 'geoapify_rooftop', provider: 'Geoapify', confidence: '0.8', confidence_band: 'medium',
  } });
  const panel = page.locator('.map-summary');
  if (width === 1440) {
    await page.goto(`./#/map?selected=${id}&release_id=${release}`);
    await expect(panel.locator('strong')).toHaveText(row.canonical_name);
    await expect(panel.locator('p')).toHaveText(['Processing', 'Synthetic locality, Denmark']);
    await expect(panel.getByRole('link')).toHaveCount(1);
    await panel.getByRole('link', { name: 'View full record', exact: true }).click();
  } else {
    await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  }
  const full = page.locator('.public-record');
  await expect(full.locator('.record-locality')).toHaveText(width === 375 ? 'Denmark' : 'Synthetic locality, Denmark');
  await expect(full.locator('.compact-source .direct-source')).toHaveAttribute('href', row.provenance_source_url);
  await expect(full.locator('.compact-source .direct-source')).toBeVisible();
  await expect(full.getByText('Precision', { exact: true })).toBeVisible();
  await expect(full.locator('.location-details')).toHaveAttribute('open', '');
  await expect(full.getByText('Geocoding provider', { exact: true })).toBeVisible();
  await expect(full.getByText('Geoapify', { exact: true })).toBeVisible();
  await expect(full.locator('.location-details')).toContainText('provider score');
  await expect(full.getByRole('link', { name: 'Open in maps', exact: true })).toHaveCount(0);
  await expect(full.getByRole('link', { name: 'Open in Map', exact: true })).toHaveAttribute('href', new RegExp(`release_id=${release}`));
  const sourceFacts = full.locator('details').filter({ has: page.locator('summary', { hasText: /^Source facts$/ }) });
  const sourceReview = full.locator('details').filter({ has: page.locator('summary', { hasText: /^Source and review$/ }) });
  await expect(sourceFacts).toHaveAttribute('open', '');
  await expect(sourceReview).toHaveAttribute('open', '');
  await expect(full.getByText('Synthetic former name', { exact: true })).toBeVisible();
  await sourceFacts.locator('summary').click();
  await expect(full.getByText('Synthetic former name', { exact: true })).toBeHidden();
  await expect(full.getByText('Government-sourced', { exact: true })).toBeVisible();
  await expect(full.locator('.compact-source .direct-source')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await full.getByRole('link', { name: 'Back to map', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`#/map\\?.*release_id=${release}`));
  await expect(page.getByRole('button', { name: 'Search map' })).toBeVisible();
});

test('long reference-provider attributions remain readable in mobile facility details', async ({page}) => {
  const provider='Synthetic official reference citation; '.repeat(12).slice(0,324);
  await page.setViewportSize({width:320,height:760});
  await mockPublicRecord(page,{display_precision:'approximate',geometry_provenance:{origin:'verified_coarse_reference',provider,reference_source_id:'synthetic-reference'}});
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  const full=page.locator('.public-record');
  await expect(full.getByText(provider,{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

for(const [bounds,lower,upper,text] of [['exclusive_upper',null,1000,'Less than 1,000 animals'],['inclusive_lower_exclusive_upper',1000,10000,'1,000 to less than 10,000 animals'],['inclusive_lower_unbounded',100000,null,'100,000 or more animals']] as const) test(`verified slaughter estimate preserves exact 360-day ${bounds} bounds in the full record`,async({page})=>{
    await mockPublicRecord(page,{derived_source_volume_ranges:[{...facts.derived_source_volume_ranges[0],bounds,lower,upper},facts.derived_source_volume_ranges[1]]});
    await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
    const full=page.locator('.public-record');
    await expect(full.locator('.slaughter-estimate')).toHaveText(`Estimated animals slaughtered (last 360 days) · ${text}`);
    await expect(full.locator('.slaughter-estimate a')).toHaveCount(0);
    await expect(full.locator('.source-facts').getByRole('link',{name:'Source codebook',exact:true})).toHaveAttribute('href','https://example.test/codebook');
    await expect(full.locator('.source-facts')).toContainText('10,000 to less than 100,000 pounds/month');await expect(full.locator('.source-facts dt').filter({hasText:'Estimated animals slaughtered'})).toHaveCount(0);
    await expect(full.locator('.slaughter-estimate')).not.toContainText(/365|per year|annually/);
});

test('missing slaughter range never becomes an estimate from processing volume',async({page})=>{
  await mockPublicRecord(page,{derived_source_volume_ranges:[facts.derived_source_volume_ranges[1]]});
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  const full=page.locator('.public-record');
  await expect(full.getByRole('heading',{name:row.canonical_name,exact:true})).toBeVisible();
  await expect(full.locator('.slaughter-estimate')).toHaveCount(0);
  await expect(full.locator('.source-facts')).toContainText('10,000 to less than 100,000 pounds/month');
});

test('a verified slaughter range keeps its codebook in Source facts even without other source rows', async ({ page }) => {
  await mockPublicRecord(page, {
    alternate_names: undefined, species_slaughtered: undefined, establishment_number: undefined,
    derived_source_volume_ranges: [facts.derived_source_volume_ranges[0]],
  });
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  const sourceFacts = page.getByRole('tabpanel', { name: 'Details' }).locator('.source-facts');
  await expect(sourceFacts).toHaveAttribute('open', '');
  await expect(sourceFacts.getByRole('link', { name: 'Source codebook' })).toHaveAttribute('href', 'https://example.test/codebook');
  await expect(sourceFacts.locator('dl')).toHaveCount(0);
});

async function mockPublicRecord(page: Page, overrides: Record<string, unknown> = {}, options: { failFirstReport?: boolean; annualHistory?: boolean } = {}) {
  const detailFields = new Set(['alternate_names','species_slaughtered','processing_activities','source_volume_categories','derived_source_volume_ranges','aphis_annual_reports','aphis_dated_inspections','establishment_id','establishment_number','grant_date','native_activity_code','native_activity_label']);
  const listOverrides = Object.fromEntries(Object.entries(overrides).filter(([key])=>!detailFields.has(key)));
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  await page.route('https://server.arcgisonline.com/**', route => route.abort());
  let reportFailureRemaining = options.failFirstReport ? 1 : 0;
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith('/api/')) return route.fallback();
    let body: unknown;
    if (path === '/api/v2/releases/manifest') body = { api_version: 'v2', data: { release_id: release, profile: 'official', manifest: {}, manifest_sha256: 'a'.repeat(64), suppression_generation: 1 } };
    else if (path === `/api/v2/locations/${id}`) body = { api_version: 'v2', data: { ...row, ...facts, ...overrides }, meta };
    else if (path === '/api/v2/locations') body = { api_version: 'v2', data: [{ ...row, ...listOverrides }], meta: { ...meta, coverage_note: 'Synthetic test coverage.', total_count: 1, next_cursor: null } };
    else if (path === `/api/v2/locations/${id}/aphis-report-links`) {
      const params = new URL(route.request().url()).searchParams;
      const kind = params.get('kind');
      const olderAnnual = kind === 'annual_reports' && params.has('cursor');
      if (kind === 'annual_reports' && reportFailureRemaining > 0) { reportFailureRemaining -= 1; return route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }); }
      body = { api_version: 'v2', data: kind === 'annual_reports' ? [{
        reference_id: olderAnnual ? '550e8400-e29b-41d4-a716-446655440003' : '550e8400-e29b-41d4-a716-446655440001', source_id: 'us.aphis.annual-reports', evidence_type: 'annual_reports',
        event_date: null, event_period: olderAnnual ? '2024' : '2025',
        source_url: 'https://direct.aphis.usda.gov/awa/research-facility-report/annual-summary',
        report_url: 'https://www.aphis.usda.gov/sites/default/files/annual-report.pdf', column_e_url: null,
        reference_origin: 'release_approved_evidence', match_method: 'exact_source_identifier',
      }] : [{
        reference_id: '550e8400-e29b-41d4-a716-446655440002', source_id: 'us.inspections', evidence_type: 'inspections',
        event_date: '2025-02-03', event_period: null,
        source_url: 'https://direct.aphis.usda.gov/awa/search/inspection-reports',
        report_url: null, column_e_url: null,
        reference_origin: 'release_approved_evidence', match_method: 'exact_source_identifier',
      }], meta: { profile: 'official', release_id: release, ruleset_version: 'synthetic-rules', kind, limit: 20, next_cursor: options.annualHistory && kind === 'annual_reports' && !olderAnnual ? '550e8400-e29b-41d4-a716-446655440001' : null, public_projection: true } };
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

test('Spanish processing summary is deduplicated in the full record', async ({ page }) => {
  const expectedSummary = 'El procesamiento de aves prepara su carne para la venta o para su transformación posterior. La fuente registra el sacrificio de aves de corral y el procesamiento de carne de pollo.';
  await page.addInitScript(() => localStorage.setItem('uec-language', 'es'));
  await mockPublicRecord(page);
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  const full = page.locator('.public-record');
  await expect(full.getByText('Procesamiento y preparación', { exact: true })).toHaveCount(1);
  const fullActivities = full.locator('.classification-summary .summary');
  await expect(fullActivities).toHaveText(expectedSummary);
  await expect(fullActivities).not.toHaveText(/(?:^|,\s*)Procesamiento(?:,\s*|$)/);
});

for (const width of [320,1440]) test(`APHIS carrier explanation is readable at ${width}px with original classification in Details`,async({page})=>{
  await page.setViewportSize({width,height:900});
  await mockPublicRecord(page,{provenance_source_id:'us.aphis',category:'other_regulated_premises',taxonomy_display_category:'other_regulated_premises',taxonomy_primary_categories:['other_regulated_premises'],taxonomy_leaf_activities:[{key:'general_food_business',label:'General food business'}],taxonomy_assignments:[],native_activity_code:'Class T',native_activity_label:'Class T - Carrier',processing_activities:{},species_slaughtered:{},derived_source_volume_ranges:undefined});
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  const detail=page.locator('.public-record'),explanation=detail.locator('[data-classification-explanation]');
  await expect(explanation).toHaveText('APHIS Class T carriers transport regulated animals for hire, including by road, air, rail or sea.');
  await expect(explanation).not.toContainText(/laborator|Recorded activities/);
  await expect(page.getByText('Local V2 list response was rejected.',{exact:true})).toHaveCount(0);
  const classificationDetails=detail.locator('.classification-disclosure details');
  await expect(classificationDetails).toBeHidden();
  if(process.env.UEC_CLASSIFICATION_CAPTURE_DIR) await page.screenshot({path:`${process.env.UEC_CLASSIFICATION_CAPTURE_DIR}/classification-carrier-${width}.png`});
  await detail.getByRole('tab', { name: 'Details', exact: true }).click();
  await expect(classificationDetails).toHaveAttribute('open','');
  await expect(classificationDetails).toContainText('Class T - Carrier');
  await expect(detail.getByRole('link',{name:'APHIS classification guide',exact:true})).toHaveAttribute('href','https://www.aphis.usda.gov/animal_welfare/downloads/graybook.pdf');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});

test('French research narrative labels the exact reported count and year, without a death claim',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.addInitScript(()=>localStorage.setItem('uec-language','fr'));
  await mockPublicRecord(page,{provenance_source_id:'us.aphis',category:'research_and_animal_use',taxonomy_display_category:'research_and_animal_use',taxonomy_primary_categories:['research_and_animal_use'],taxonomy_leaf_activities:[{key:'research',label:'Research'}],taxonomy_assignments:[],native_activity_code:'Class R',processing_activities:{},species_slaughtered:{},derived_source_volume_ranges:undefined,aphis_annual_reports:[{fiscal_year:'2025',species_counts:[{species:'Synthetic species A',count:12},{species:'Synthetic species B',count:3}],source_url:'https://example.test/annual-report',safe_provenance:{source_id:'us.aphis.annual-reports',evidence_type:'annual_reports',match_method:'exact_source_identifier',matched_identifier_types:['certificate_number']}}]});
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  const explanation=page.locator('.public-record [data-classification-explanation]');
  await expect(explanation).toContainText('Le rapport de l’exercice 2025 recense 15 animaux parmi les espèces déclarées.');
  await expect(explanation).not.toContainText(/mort|tués|sacrifi|estimated/);
  if(process.env.UEC_CLASSIFICATION_CAPTURE_DIR) await page.screenshot({path:`${process.env.UEC_CLASSIFICATION_CAPTURE_DIR}/classification-research-fr-mobile.png`});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});

test('city-level geocoding keeps its approximation and actual provider score in one Location section', async ({ page }) => {
  await mockPublicRecord(page, { display_precision: 'provider_locality_approximate', geometry_provenance: {
    origin: 'provider_geocode', method: 'geoapify_forward', provider: 'Synthetic geocoder', confidence: '0.72', confidence_band: 'medium',
  } });
  await page.goto(`./#/map?selected=${id}&release_id=${release}`);
  const panel = page.locator('.map-summary');
  await expect(panel).toBeVisible();
  await expect(panel.getByText('Approximate location', { exact: true })).toHaveCount(0);
  await panel.getByRole('link', { name: 'View full record', exact: true }).click();
  const full = page.locator('.public-record');
  await expect(full).toContainText('Approximate location');
  await expect(full.locator('.location-details')).toHaveAttribute('open', '');
  await expect(full.getByText('Geoapify forward', { exact: true })).toBeVisible();
  await expect(full.getByText('Synthetic geocoder', { exact: true })).toBeVisible();
  await expect(full.getByText('55, 10', { exact: true })).toBeVisible();
  await expect(full.getByText('Address', { exact: true })).toHaveCount(0);
  await expect(full.locator('.location-preview')).toHaveAttribute('aria-label', 'Satellite location preview');
  const pageOrder = await full.evaluate(root => {
    const tabs = root.querySelector('.record-tabs');
    const preview = root.querySelector('.location-preview');
    const activities = root.querySelector('#activities-heading');
    return Boolean(tabs && preview && activities &&
      (activities.compareDocumentPosition(preview) & Node.DOCUMENT_POSITION_FOLLOWING) &&
      (preview.compareDocumentPosition(tabs) & Node.DOCUMENT_POSITION_FOLLOWING));
  });
  expect(pageOrder).toBe(true);
  await expect(full.locator('.location-preview .map')).toHaveAttribute('data-pin-loaded', 'true');
  await expect(full.getByText('0.72 (provider score) · Medium', { exact: true })).toBeVisible();
  await expect(full.locator('#location-heading')).toHaveText('Location');
  await full.locator('.location-preview').getByRole('link', { name: 'Open in Map', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`#/map\\?.*selected=${id}.*release_id=${release}`));
  await expect(page.locator('.map-summary strong')).toHaveText(row.canonical_name);
});

test('unmapped public records do not create a location map', async ({ page }) => {
  await mockPublicRecord(page, { display_precision: 'unmapped', latitude: null, longitude: null });
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  await expect(page.getByRole('heading', { name: row.canonical_name })).toBeVisible();
  await expect(page.locator('.location-preview')).toHaveCount(0);
});

for(const state of ['empty','populated','error'] as const) test(`facility Connections tab reflects for ${state} data`,async({page})=>{
  await mockPublicRecord(page);
  await page.route('**/api/v2/graph/**',route=>{
    if(state==='error')return route.fulfill({status:503,json:{}});
    const endpoint=(entity_type:string,entity_id:string,display_name:string)=>({entity_type,entity_id,display_name,source_id:'synthetic-source',identifier_type:'synthetic',source_identifier:entity_id});
    const edge={connection_edge_id:'550e8400-e29b-41d4-a716-446655440009',from:endpoint('facility',id,'Synthetic facility'),to:endpoint('organization','550e8400-e29b-41d4-a716-446655440008','Synthetic research organization'),relationship_type:'source_assertion',connection_type:'exact',confidence:1,confidence_band:'exact',match_method:'exact_source_identifier',signals:{},contradictions:[],provenance:{source_ids:['synthetic-source'],observed_at:observed,release_id:release},source_references:[{source_id:'synthetic-source'}],observed_at:observed,computed_at:observed,ruleset:'synthetic-rules',conflicting:false,publication_warning:'Synthetic connection fixture',disclaimer:'Synthetic evidence only'};
    return route.fulfill({json:{api_version:'v2-graph-v1',data:state==='populated'?[edge]:[],meta:{...meta,limit:20,page_max:100,next_cursor:null,public_projection:true}}});
  });
  const lookup = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v2/graph/connections');
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  await lookup;
  const tab = page.getByRole('tab', { name: 'Connections', exact: true });
  if (state === 'empty') { await expect(tab).toHaveCount(0); return; }
  await tab.click();
  const panel = page.getByRole('tabpanel', { name: 'Connections', exact: true });
  if (state === 'populated') await expect(panel.getByText('Synthetic research organization', { exact: true })).toBeVisible();
  else await expect(panel.getByRole('button', { name: 'Retry', exact: true })).toBeVisible();
});

test('a failed map image leaves the facility record readable and announces the map limitation', async ({ page }) => {
  await page.route('**/v1-pins/**', route => route.abort());
  await mockPublicRecord(page);
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  await expect(page.locator('.location-preview')).toBeVisible();
  await expect(page.locator('.location-preview [role="status"]')).toHaveText('Location map unavailable.');
  await expect(page.locator('.public-record').getByRole('heading', { name: 'Classification' })).toBeVisible();
});

test('APHIS source records load both report lists automatically and retry independently', async ({ page }) => {
  const kinds: (string | null)[] = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname === `/api/v2/locations/${id}/aphis-report-links`) kinds.push(url.searchParams.get('kind'));
  });
  await mockPublicRecord(page, { provenance_source_id: 'us.aphis' }, { failFirstReport: true });
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  await expect(page.getByRole('heading', { name: 'APHIS reports' })).toBeVisible();
  const annual = page.getByRole('region', { name: 'Annual reports', exact: true });
  const inspections = page.getByRole('region', { name: 'Inspection reports', exact: true });
  await expect(annual.getByRole('alert')).toContainText('Reports could not be loaded.');
  await expect(inspections.getByText('Inspection · 2025-02-03', { exact: true })).toBeVisible();
  expect(kinds).toEqual(['annual_reports', 'inspections']);
  await annual.getByRole('button', { name: 'Retry' }).click();
  await expect(annual.getByText('Annual report · FY2025', { exact: true })).toBeVisible();
  await expect(annual.getByRole('link', { name: 'Open report', exact: true })).toBeVisible();
  expect(kinds).toEqual(['annual_reports', 'inspections', 'annual_reports']);
  const reports = page.getByRole('tab', { name: 'Reports', exact: true });
  await expect(reports).toHaveAttribute('aria-selected', 'true');
  await reports.focus();
  await reports.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Connections', exact: true })).toHaveCount(0);
  await expect(annual).not.toBeVisible();
  const details = page.getByRole('tab', { name: 'Details', exact: true });
  await expect(details).toBeFocused();
  await expect(page.getByRole('tabpanel', { name: 'Details' })).toBeVisible();
  await details.press('Home');
  await expect(reports).toBeFocused();
  await expect(annual.getByText('Annual report · FY2025', { exact: true })).toBeVisible();
  expect(kinds).toEqual(['annual_reports', 'inspections', 'annual_reports']);
});

for (const [certificateClass, kinds] of [
  ['Class R', ['annual_reports', 'annual_reports', 'inspections']],
  ['Class T', ['inspections']],
] as const) test(`APHIS ${certificateClass} loads applicable report history automatically`, async ({ page }) => {
  const requests: (string | null)[] = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname === `/api/v2/locations/${id}/aphis-report-links`) requests.push(url.searchParams.get('kind'));
  });
  await mockPublicRecord(page, {
    provenance_source_id: 'us.aphis', native_activity_code: certificateClass,
    establishment_id: `aphis-registration:00-${certificateClass.slice(-1)}-0000`,
  }, { annualHistory: true });
  await page.goto(`./#/records/${id}?profile=official&release_id=${release}`);
  const annual = page.getByRole('region', { name: 'Annual reports', exact: true });
  await expect(page.getByText('Inspection · 2025-02-03', { exact: true })).toBeVisible();
  if (certificateClass === 'Class R') {
    await expect(annual.getByText('Annual report · FY2025', { exact: true })).toBeVisible();
    await expect(annual.getByText('Annual report · FY2024', { exact: true })).toBeVisible();
  } else {
    await expect(annual.getByText('Annual reports are for research facilities.', { exact: true })).toBeVisible();
  }
  expect(requests).toEqual(kinds);
});
