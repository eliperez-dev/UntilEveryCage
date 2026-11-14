import { expect, test, type Page } from '@playwright/test';

const release = 'synthetic-mobile-discovery';
const stamp = '2026-10-18T00:00:00Z';
const categories = ['slaughter','animal_keeping_and_production','processing_and_preparation','research_and_animal_use','other_regulated_premises','unclassified'];
const rows = Array.from({length:132}, (_, index) => ({
  facility_id:`550e8400-e29b-41d4-a716-${String(index).padStart(12,'0')}`,
  canonical_name:`Synthetic facility ${String(index + 1).padStart(3,'0')}`,
  category:categories[index % 6], country_code:'US', city:'Sample district',
  display_precision:index >= 130 ? 'unmapped' : index % 2 ? 'approximate' : 'source_reported',
  latitude:index >= 130 ? null : 39.2 + index % 10 / 100,
  longitude:index >= 130 ? null : -94.5 + Math.floor(index / 10) / 100,
  source_type:'official', publication_profile:'official', factual_review_status:'reviewed', privacy_screening_status:'passed',
  project_approval:'approved', reviewer_role:null, publication_warning:null, first_observed_at:null,
  last_observed_at:stamp, observation_count:1, lifecycle_status:'active_observed', provenance_source_id:`synthetic-source-${index % 2}`,
  provenance_source:null, provenance_source_name:'Example register', provenance_source_url:'https://example.test/register',
  provenance_retrieved_at:stamp, source_rights_status:'cleared', release_id:release, release_ruleset_version:'synthetic-rules',
  taxonomy_display_category:categories[index % 6], taxonomy_primary_categories:[categories[index % 6]], taxonomy_leaf_activities:[], taxonomy_assignments:[],
}));

async function install(page:Page) {
  await page.route('https://**/*', route => process.env.UEC_MOBILE_CAPTURE_DIR && /^https:\/\/(?:tile\.openstreetmap\.org|server\.arcgisonline\.com)\//.test(route.request().url()) ? route.continue() : route.abort());
  const identity = {profile:'official',release_id:release,manifest_sha256:'a'.repeat(64),suppression_generation:1};
  const meta = {profile:'official',release_id:release,ruleset_version:'synthetic-rules',release_created_at:stamp};
  const calls:{path:string;method:string;params:Record<string,string>}[] = [];
  await page.route('**/api/v2/**', route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    const params = Object.fromEntries(url.searchParams);
    calls.push({path,method:request.method(),params});
    const filtered = rows.filter(row => (!params.q || row.canonical_name.toLowerCase().includes(String(params.q).toLowerCase())) &&
      (!params.category_keys || String(params.category_keys).split(',').includes(row.category!)) &&
      (!params.display_precision || String(params.display_precision).split(',').includes(row.display_precision)) &&
      (!params.min_lon || (row.longitude !== null && row.latitude !== null && row.longitude >= Number(params.min_lon) && row.longitude <= Number(params.max_lon) && row.latitude >= Number(params.min_lat) && row.latitude <= Number(params.max_lat))) &&
      (!params.radius_km || row.latitude !== null) && (!params.us_state || row.latitude !== null));
    let body:unknown;
    if(path === '/api/v2/releases/manifest') body = {api_version:'v2',data:{...identity,manifest:{}}};
    else if(path === '/api/v2/locations') body = {api_version:'v2',data:filtered.slice(params.cursor ? 100 : 0,params.cursor ? 200 : 100),meta:{...meta,total_count:filtered.length,next_cursor:filtered.length > 100 && !params.cursor ? 'synthetic-page-two' : null,coverage_note:'Synthetic interface checks.'}};
    else if(path.startsWith('/api/v2/locations/')) body = {api_version:'v2',data:rows.find(row => row.facility_id === path.split('/').pop()),meta};
    else if(path === '/api/v2/map/feed') body = {api_version:'v2',data:{type:'FeatureCollection',features:rows.filter(row => row.latitude !== null).map(row => ({type:'Feature',id:row.facility_id,geometry:{type:'Point',coordinates:[row.longitude,row.latitude]},properties:{facility_id:row.facility_id,source_id:row.provenance_source_id,category_key:row.category,category_keys:[row.category],precision:row.display_precision,weight:1}}))},meta:{...identity,feature_count:130,public_record_count:132,unmapped_count:2,release_label:'Synthetic area fixture',dataset_version:'synthetic'}};
    else if(path === '/api/v2/map/matches') body = {api_version:'v2',data:{facility_ids:filtered.filter(row => row.latitude !== null).map(row => row.facility_id)},meta:{...identity,total_count:filtered.length,mapped_count:filtered.filter(row => row.latitude !== null).length}};
    else if(path === '/api/v2/discovery/facets') body = {api_version:'v2',dimensions:{country_code:[{value:'US',count:132},{value:'FR',count:0}],source_id:[{value:'synthetic-source-0',label:'Example register A',count:66},{value:'synthetic-source-1',label:'Example register B',count:66}]},meta:{...meta,filters:{},coverage_scope:'Synthetic checks',count_semantics:'Matching synthetic records'}};
    else if(path.startsWith('/api/v2/graph/')) body = {api_version:'v2-graph-v1',data:[],meta:{...meta,limit:20,page_max:100,next_cursor:null,public_projection:true}};
    else return route.fulfill({status:404,json:{}});
    return route.fulfill({json:body});
  });
  return calls;
}
async function open(page: Page) {
  await page.goto(`./#/map?release_id=${release}&list=closed&lat=38.8&lon=-94.45&z=8`);
  await expect(page.locator('.maplibregl-canvas')).toBeVisible({ timeout: 15_000 });
}

for (const width of [320, 390, 1440]) {
  test(`search is stable at ${width}px and only sends submitted queries`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 1440 ? 900 : 812 });
    const calls = await install(page);
    await open(page);
    const query = page.getByRole('combobox', { name: 'Search across public release records' });
    const search = page.getByRole('search');
    const filters = page.getByRole('button', { name: 'Filters', exact: true });
    const results = page.locator('#field-record-list');
    const searchBox = (await search.boundingBox())!;
    const filterBox = (await filters.boundingBox())!;
    expect(filterBox.x).toBeCloseTo(searchBox.x + searchBox.width, 0);
    expect(filterBox.height).toBeGreaterThanOrEqual(44);

    await query.fill('e');
    await expect(results).toBeHidden();
    await query.press('Enter');
    await expect(page.getByRole('status').filter({ hasText: 'Enter at least 3 letters or numbers.' })).toBeVisible();
    expect(calls.filter(call => call.params.q)).toHaveLength(0);

    await query.fill('California');
    await expect(page.getByRole('option', { name: 'California State' })).toBeVisible();
    if (width !== 1440) {
      const phoneSearch = page.locator('.phone-search');
      await expect(phoneSearch.getByRole('button', { name: 'Cancel' })).toBeVisible();
      await expect(page.locator('.map-stage')).toHaveAttribute('inert', '');
      await expect(page.locator('.field-masthead')).toHaveAttribute('inert', '');
      await expect(filters).toBeHidden();
      await page.evaluate(() => {
        const viewport = window.visualViewport!;
        // Phone keyboards shrink the visual viewport without resizing the layout viewport.
        Object.defineProperty(viewport, 'height', { configurable: true, value: 230 });
        Object.defineProperty(viewport, 'offsetTop', { configurable: true, value: 96 });
        viewport.dispatchEvent(new Event('scroll'));
        viewport.dispatchEvent(new Event('resize'));
      });
      const california = page.getByRole('option', { name: 'California State' });
      await expect(california).toBeInViewport();
      await expect(query).toBeFocused();
      await expect(query).toHaveValue('California');
      await expect.poll(() => phoneSearch.boundingBox()).toMatchObject({ y: 96, height: 230 });
      await expect(results).toBeHidden();
      await phoneSearch.getByRole('button', { name: 'Cancel' }).click();
      await expect(filters).toBeVisible();
      await expect(query).toHaveValue('');
      await expect(page.locator('.map-stage')).not.toHaveAttribute('inert', '');
      await page.evaluate(() => {
        const viewport = window.visualViewport!;
        Reflect.deleteProperty(viewport, 'height');
        Reflect.deleteProperty(viewport, 'offsetTop');
        viewport.dispatchEvent(new Event('resize'));
      });
    }
    await query.fill('slaughter houses in oh');
    await expect(page.getByRole('option', { name: 'Ohio State' })).toBeVisible();
    expect(calls.filter(call => call.params.q || call.params.us_state)).toHaveLength(0);
    await query.press('ArrowDown');
    await query.press('Enter');
    await expect(results).toBeVisible();
    await expect(results.getByRole('button', { name: /Clear map area: Ohio/ })).toBeVisible();
    await expect.poll(() => calls.filter(call => call.params.us_state === 'US-OH').map(call => call.path).sort())
      .toEqual(['/api/v2/locations', '/api/v2/map/matches']);
    expect(calls.filter(call => call.params.us_state === 'US-OH').every(call => call.params.category_keys === 'slaughter' && !call.params.q)).toBe(true);
    expect(page.url()).not.toContain('slaughter%20houses');

    await query.fill('France');
    await expect(page.getByRole('option', { name: 'France Country' })).toBeVisible();
    await page.getByRole('option', { name: 'France Country' }).click();
    await expect.poll(() => calls.some(call => call.params.country_code === 'FR')).toBe(true);
    await expect(results.getByRole('button', { name: /Clear map area: Ohio/ })).toBeHidden();
    await results.getByRole('button', { name: 'Remove filter: France' }).click();
    await results.getByRole('button', { name: 'Remove filter: Slaughter' }).click();

    await query.fill('Synthetic facility 00');
    expect(calls.filter(call => call.params.q)).toHaveLength(0);
    await search.getByRole('button', { name: 'Search map' }).click();
    await expect.poll(() => calls.filter(call => call.params.q === 'Synthetic facility 00').map(call => call.path).sort())
      .toEqual(['/api/v2/locations', '/api/v2/map/matches']);
  });
}

test.describe('touch search', () => {
  test.use({ viewport: { width: 390, height: 812 }, hasTouch: true, isMobile: true });
  test.skip(({ browserName }) => browserName === 'firefox', 'Firefox does not support Playwright mobile emulation.');

  test('a phone city suggestion searches nearby and returns to the map', async ({ page }) => {
    const calls = await install(page);
    await open(page);
    const query = page.getByRole('combobox', { name: 'Search across public release records' });
    await query.tap();
    await query.fill('San Diego');
    const suggestion = page.getByRole('option', { name: /^San Diego, California, United States City$/ });
    await expect(suggestion).toBeVisible();
    expect(calls.some(call => call.params.q || call.params.radius_km)).toBe(false);
    await suggestion.tap();
    await expect(page.locator('.phone-search')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Clear map area: San Diego, California, United States · 16 miles' })).toBeVisible();
    await expect.poll(() => calls.filter(call => call.params.radius_km === '25').map(call => call.path).sort())
      .toEqual(['/api/v2/locations', '/api/v2/map/matches']);
    expect(calls.some(call => call.params.q)).toBe(false);
  });
});

test('filters stage changes and use readable activity labels', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 812 });
  const calls = await install(page);
  await open(page);
  const count = () => calls.filter(call => call.path === '/api/v2/locations').length;
  await expect.poll(count).toBeGreaterThan(0);
  const filters = page.getByRole('button', { name: 'Filters', exact: true });
  const panel = page.getByRole('region', { name: 'Filters', exact: true });
  const slaughter = panel.getByRole('checkbox', { name: 'Slaughter', exact: true });
  const before = count();
  await filters.click();
  await expect(panel).toBeVisible();
  expect(await slaughter.locator('..').evaluate(node => getComputedStyle(node).fontSize)).toBe('15px');
  await slaughter.check();
  await expect(panel.getByText('Location precision', { exact: true })).toHaveCount(0);
  await panel.getByRole('button', { name: 'Close', exact: true }).click();
  expect(count()).toBe(before);
  await filters.click();
  await expect(slaughter).not.toBeChecked();
  await slaughter.check();
  await panel.getByRole('button', { name: 'Apply filters', exact: true }).click();
  await expect.poll(count).toBe(before + 1);
  await expect(page.locator('.mobile-record-list [data-record-id]')).toHaveCount(22);
});
