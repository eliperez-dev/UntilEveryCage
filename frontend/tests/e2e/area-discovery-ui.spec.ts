import { expect, test, type Page } from '@playwright/test';

const release = 'synthetic-area-discovery';
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
  await page.route('https://**/*', route => process.env.UEC_AREA_CAPTURE_DIR && /^https:\/\/(?:tile\.openstreetmap\.org|server\.arcgisonline\.com)\//.test(route.request().url()) ? route.continue() : route.abort());
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
      (!params.radius_km || row.latitude !== null));
    let body:unknown;
    if(path === '/api/v2/releases/manifest') body = {api_version:'v2',data:{...identity,manifest:{}}};
    else if(path === '/api/v2/locations') body = {api_version:'v2',data:filtered.slice(params.cursor ? 100 : 0,params.cursor ? 200 : 100),meta:{...meta,total_count:filtered.length,next_cursor:filtered.length > 100 && !params.cursor ? 'synthetic-page-two' : null,coverage_note:'Synthetic interface checks.'}};
    else if(path.startsWith('/api/v2/locations/')) body = {api_version:'v2',data:rows.find(row => row.facility_id === path.split('/').pop()),meta};
    else if(path === '/api/v2/map/feed') body = {api_version:'v2',data:{type:'FeatureCollection',features:rows.filter(row => row.latitude !== null).map(row => ({type:'Feature',id:row.facility_id,geometry:{type:'Point',coordinates:[row.longitude,row.latitude]},properties:{facility_id:row.facility_id,source_id:row.provenance_source_id,category_key:row.category,category_keys:[row.category],precision:row.display_precision,weight:1}}))},meta:{...identity,feature_count:130,public_record_count:132,unmapped_count:2,release_label:'Synthetic area fixture',dataset_version:'synthetic'}};
    else if(path === '/api/v2/map/matches') body = {api_version:'v2',data:{facility_ids:filtered.filter(row => row.latitude !== null).map(row => row.facility_id)},meta:{...identity,total_count:filtered.length,mapped_count:filtered.filter(row => row.latitude !== null).length}};
    else if(path === '/api/v2/discovery/facets') body = {api_version:'v2',dimensions:{country_code:[{value:'US',count:132}],source_id:[{value:'synthetic-source-0',label:'Example register A',count:66},{value:'synthetic-source-1',label:'Example register B',count:66}]},meta:{...meta,filters:{},coverage_scope:'Synthetic checks',count_semantics:'Matching synthetic records'}};
    else if(path.startsWith('/api/v2/graph/')) body = {api_version:'v2-graph-v1',data:[],meta:{...meta,limit:20,page_max:100,next_cursor:null,public_projection:true}};
    else return route.fulfill({status:404,json:{}});
    return route.fulfill({json:body});
  });
  return calls;
}
async function open(page:Page) {
  await page.goto(`./#/map?release_id=${release}&list=closed&lat=39.25&lon=-94.45&z=8`);
  await expect(page.locator('.maplibregl-canvas')).toBeVisible({timeout:15_000});
  await expect(page.locator('.map-navigation .dimension-button')).toBeEnabled();
}

test('area overview uses the complete mapped set, category narrows both views, and update preserves query', async ({page}) => {
  await page.setViewportSize({width:1440,height:900}); const calls = await install(page); await open(page);
  const canvas = await page.locator('.map-stage').boundingBox();
  await page.getByRole('button',{name:'Search this area',exact:true}).click();
  await expect(page.locator('.results')).toBeVisible();
  const summary = page.locator('.area-summary'); await expect(summary.locator('.area-total strong')).toHaveText('130');
  await expect(page.locator('[data-record-id]')).toHaveCount(100);
  await expect(summary.locator('.area-details')).not.toHaveAttribute('open','');
  const first = page.locator('[data-record-id]').first();
  await expect(first).toBeInViewport(); expect((await first.boundingBox())!.height).toBeGreaterThan(44);
  expect((await page.locator('.record-list').boundingBox())!.height).toBeGreaterThan(1000);
  await expect(page.locator('.csv-download')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Fit results',exact:true})).toHaveCount(0);
  if(process.env.UEC_AREA_CAPTURE_DIR) {
    await expect.poll(() => page.evaluate(() => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return map?.getLayer('v1-source-pins') ? map.queryRenderedFeatures({layers:['v1-source-pins','approx-reference-pins','approx-reference-points']}).length : 0; }), {timeout:15_000}).toBeGreaterThan(0);
    await page.screenshot({path:`${process.env.UEC_AREA_CAPTURE_DIR}/area-desktop.png`});
  }
  await summary.locator('.area-details > summary').click(); await expect(summary.getByRole('button',{name:'Processing: 22',exact:true})).toBeVisible();
  await expect(summary.locator('.area-evidence')).toContainText('2 sources');
  await expect(summary.locator('dd')).toHaveText(['65','65']);
  await summary.getByRole('button',{name:'Processing: 22',exact:true}).click();
  await expect(summary.locator('.area-total strong')).toHaveText('22'); await expect(page.locator('[data-record-id]')).toHaveCount(22);
  await expect.poll(() => calls.filter(call => call.path === '/api/v2/map/matches').at(-1)?.params.category_keys).toBe('processing_and_preparation');
  await page.locator('#field-search').fill('Synthetic');
  await expect(summary.locator('.area-total strong')).toHaveText('22');
  await page.getByRole('button',{name:'Search this area',exact:true}).click();
  await expect(page.locator('#field-search')).toHaveValue('Synthetic');
  await expect(page.locator('.filter-chips')).toContainText('Processing');
  await summary.getByRole('button',{name:'Explore full map',exact:true}).click();
  await expect(page.locator('.results')).toBeHidden(); await expect(page.locator('#field-search')).toHaveValue('Synthetic');
  await page.locator('#field-search').click(); await expect(summary).toHaveCount(0); await expect(page.locator('.filter-chips')).toContainText('Processing');
  expect(await page.locator('.map-stage').boundingBox()).toEqual(canvas);
});

test('public exact destinations offer external maps while approximate records do not', async ({page}) => {
  await page.setViewportSize({width:390,height:844}); await install(page); await open(page);
  const handle = page.locator('.mobile-sheet-handle'); await handle.click(); await handle.focus(); await page.keyboard.press('End');
  await page.locator('[data-record-id]').nth(0).click(); await expect(handle).toHaveAttribute('data-sheet-state','expanded');
  const maps = page.getByRole('link',{name:'Open in maps',exact:true});
  await expect(maps).toHaveAttribute('href','https://www.google.com/maps/search/?api=1&query=39.2%2C-94.5');
  await expect(maps).toHaveAttribute('rel','noopener noreferrer'); await expect(maps).toHaveAttribute('referrerpolicy','no-referrer');
  if(process.env.UEC_AREA_CAPTURE_DIR) await page.screenshot({path:`${process.env.UEC_AREA_CAPTURE_DIR}/maps-mobile.png`});
  await page.locator('.back-to-results').click();
  await page.locator('[data-record-id]').nth(1).click(); await expect(maps).toHaveCount(0); await expect(page.getByRole('button',{name:'Show on map',exact:true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
});

test('Your location searches 50 miles with existing query and keeps coordinates out of the route', async ({page}) => {
  await page.setViewportSize({width:320,height:844});
  await page.addInitScript(() => { (window as any).__locationCalls = 0; Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition(success:PositionCallback){(window as any).__locationCalls++; success({coords:{latitude:39.2777,longitude:-94.4333}} as GeolocationPosition)}}}); });
  const calls = await install(page); await open(page);
  expect(await page.evaluate(() => (window as any).__locationCalls)).toBe(0);
  await page.locator('.mobile-sheet-handle').click(); await page.locator('#field-search').fill('Synthetic');
  await page.getByRole('button',{name:'Your location',exact:true}).click();
  await expect(page.locator('.area-summary h2')).toHaveText('Near you');
  await expect(page.locator('.scope-radius')).toHaveText('50 mile radius');
  await expect.poll(() => calls.filter(call => call.path === '/api/v2/locations').at(-1)?.params.radius_km).toBe('80.4672');
  expect(calls.filter(call => call.path === '/api/v2/locations').at(-1)?.params.q).toBe('Synthetic');
  expect(await page.evaluate(() => (window as any).__locationCalls)).toBe(1);
  expect(page.url()).not.toMatch(/39\.2777|94\.4333|radius|latitude|longitude/);
  expect(await page.evaluate(() => JSON.stringify({local:{...localStorage},session:{...sessionStorage},state:history.state}))).not.toMatch(/39\.2777|94\.4333/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  if(process.env.UEC_AREA_CAPTURE_DIR) {
    await page.screenshot({path:`${process.env.UEC_AREA_CAPTURE_DIR}/nearby-mobile.png`});
    await page.locator('.mobile-sheet-handle').focus(); await page.keyboard.press('End');
    await page.screenshot({path:`${process.env.UEC_AREA_CAPTURE_DIR}/nearby-mobile-expanded.png`});
  }
});

test('pending and failed matching never leave a previous ready overview visible', async ({page}) => {
  await page.setViewportSize({width:1440,height:900}); await install(page); await open(page);
  await page.getByRole('button',{name:'Search this area',exact:true}).click(); await page.locator('#field-search').click();
  const summary = page.locator('.area-summary'); await expect(summary.locator('.area-total strong')).toHaveText('130');
  let fail: (() => void) | undefined;
  await page.route('**/api/v2/map/matches?**', async route => { await new Promise<void>(resolve => { fail = resolve; }); await route.fulfill({status:503,json:{error:{message:'Synthetic matching failure'}}}); });
  await page.locator('#field-search').fill('Synthetic facility 0');
  await expect(summary.getByText('Counting records…',{exact:true})).toBeVisible(); await expect(summary.locator('.area-total')).toHaveCount(0);
  await expect.poll(() => Boolean(fail)).toBe(true); fail!();
  await expect(summary.getByText('Area summary unavailable.',{exact:true})).toBeVisible(); await expect(summary.locator('.area-total')).toHaveCount(0);
});

for (const width of [320,390,1440]) test(`Places has a bounded unfilled chevron and usable expandable rows in German at ${width}px`, async ({page}) => {
  await page.setViewportSize({width,height:900}); await page.addInitScript(() => localStorage.setItem('uec-language','de'));
  await install(page); await open(page);
  if(width <= 640) { await page.locator('.mobile-sheet-handle').click(); await page.locator('.mobile-sheet-handle').focus(); await page.keyboard.press('End'); }
  await page.locator('#field-search').fill('San');
  const places = page.locator('.place-suggestions'), expand = places.locator('.places-expand');
  await expect(expand).toBeVisible(); await expect(expand).toHaveAttribute('aria-expanded','false');
  const svg = (await expand.locator('svg').boundingBox())!, button = (await expand.boundingBox())!;
  expect(svg.width).toBe(16); expect(svg.height).toBe(16); expect(button.width).toBe(44); expect(button.height).toBe(44);
  expect(await expand.locator('svg').evaluate(node => getComputedStyle(node).fill)).toBe('none');
  await expect(places.locator('li:visible')).toHaveCount(1);
  await expand.click(); await expect(expand).toHaveAttribute('aria-expanded','true'); await expect(places.locator('li:visible')).toHaveCount(5);
  await expect(places.locator('li:visible').first().getByRole('button')).toHaveCount(2);
  await expand.click(); await expect(expand).toHaveAttribute('aria-expanded','false'); await expect(places.locator('li:visible')).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  if(process.env.UEC_AREA_CAPTURE_DIR) await page.screenshot({path:`${process.env.UEC_AREA_CAPTURE_DIR}/places-${width}.png`});
});

for(const [width,height] of [[320,568],[390,844],[1280,620]]) test(`scoped search opens readable rows and paginates through the outer scroll at ${width}×${height}`,async({page})=>{
  await page.setViewportSize({width:width!,height:height!});await install(page);await open(page);
  await page.getByRole('button',{name:'Search this area',exact:true}).click();await expect(page.locator('.results')).toBeVisible();
  const handle=page.locator('.mobile-sheet-handle');if(width!<641) await expect(handle).toHaveAttribute('data-sheet-state','middle');
  const first=page.locator('[data-record-id]').first();await expect(first).toBeInViewport();
  const body=await page.locator('.list-content').boundingBox(),name=await first.locator(':scope > strong').boundingBox();
  expect(name!.y).toBeLessThan(body!.y+body!.height);expect((await first.boundingBox())!.height).toBeGreaterThan(44);
  expect(await page.locator('[data-record-id]').evaluateAll(nodes=>nodes.every(node=>node.getBoundingClientRect().height>=44))).toBe(true);
  await expect(page.locator('.activity-summary')).toHaveCount(0);
  expect((await page.locator('.area-summary').boundingBox())!.height).toBeLessThan(150);
  if(process.env.UEC_AREA_CAPTURE_DIR)await page.screenshot({path:`${process.env.UEC_AREA_CAPTURE_DIR}/compact-${width}-${height}.png`});
  await page.locator('.load-more').scrollIntoViewIfNeeded();await page.locator('.load-more').click();await expect(page.locator('[data-record-id]')).toHaveCount(130);
  await page.locator('[data-record-id]').last().scrollIntoViewIfNeeded();await expect(page.locator('[data-record-id]').last()).toBeInViewport();
  expect(await page.locator('.list-content').evaluate(node=>node.scrollHeight>node.clientHeight)).toBe(true);
  expect(await page.locator('.record-list').evaluate(node=>getComputedStyle(node).overflow)).toBe('visible');
  if(width!<641){await handle.focus();await page.keyboard.press('End');await page.locator('#field-search').fill('Synthetic');await page.locator('#field-search').press('Enter');await expect(handle).toHaveAttribute('data-sheet-state','expanded');await handle.focus();await page.keyboard.press('Home');await page.getByRole('button',{name:'Search this area',exact:true}).click();await expect(handle).toHaveAttribute('data-sheet-state','middle');}
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});

test('search settings rerun radius at the same private center and full-map exit restores the public camera',async({page})=>{
  await page.setViewportSize({width:1440,height:850});await page.addInitScript(()=>Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition(success:PositionCallback){success({coords:{latitude:39.2777,longitude:-94.4333}}as GeolocationPosition)}}}));
  const calls=await install(page);await open(page);await page.locator('#field-search').fill('Synthetic');
  const settings=page.getByRole('button',{name:'Search settings',exact:true});await settings.click();const initialPanel=page.locator('#map-search-settings');
  const visibleMap=initialPanel.getByRole('radio',{name:'Visible map',exact:true}),radius=initialPanel.getByRole('radio',{name:'Radius',exact:true});
  await expect(visibleMap).toBeChecked();await expect(initialPanel.getByRole('slider',{name:'Search radius',exact:true})).toHaveCount(0);await expect(initialPanel.locator('output')).toHaveCount(0);
  await visibleMap.focus();await page.keyboard.press('ArrowRight');await expect(radius).toBeChecked();await expect(initialPanel.getByRole('slider',{name:'Search radius',exact:true})).toBeVisible();await expect(initialPanel.locator('output')).toHaveText('50 miles');
  await page.keyboard.press('ArrowLeft');await expect(visibleMap).toBeChecked();await expect(initialPanel.getByRole('slider',{name:'Search radius',exact:true})).toHaveCount(0);
  await page.keyboard.press('Escape');await expect(settings).toHaveAttribute('aria-expanded','false');await page.getByRole('button',{name:'Your location',exact:true}).click();
  await expect(page.locator('.scope-radius')).toHaveText('50 mile radius');await settings.click();
  await expect(settings).toHaveAttribute('aria-expanded','true');const panel=page.locator('#map-search-settings');await panel.getByRole('slider',{name:'Search radius',exact:true}).fill('75');
  await expect(page.locator('.scope-radius')).toHaveText('75 mile radius');await expect.poll(()=>Number(calls.filter(call=>call.path==='/api/v2/locations').at(-1)?.params.radius_km)).toBeCloseTo(120.7008,6);
  const parameters=calls.filter(call=>call.path==='/api/v2/locations').at(-1)!.params;expect(parameters.latitude).toBe('39.2777');expect(parameters.longitude).toBe('-94.4333');expect(parameters.q).toBe('Synthetic');
  await page.keyboard.press('Escape');await expect(settings).toHaveAttribute('aria-expanded','false');await expect(settings).toBeFocused();
  await page.locator('.area-summary').getByRole('button',{name:'Explore full map',exact:true}).click();await expect(page.locator('.results')).toBeHidden();
  await expect.poll(()=>new URLSearchParams(page.url().split('?')[1]).get('lat')).toBe('39.25');
  await expect.poll(()=>page.evaluate(()=>{const c=(window as any).__UEC_LOCAL_PREVIEW_MAP__.getCenter();return [Number(c.lat.toFixed(2)),Number(c.lng.toFixed(2))]})).toEqual([39.25,-94.45]);
  await page.locator('#field-search').click();await expect(page.locator('#field-search')).toHaveValue('Synthetic');await expect(page.locator('.area-summary')).toHaveCount(0);
});
