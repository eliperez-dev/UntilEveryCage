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
  await page.goto(`./#/map?release_id=${release}&list=closed&lat=38.8&lon=-94.45&z=8`);
  await expect(page.locator('.maplibregl-canvas')).toBeVisible({timeout:15_000});
  await expect(page.locator('.map-navigation .dimension-button')).toBeEnabled();
}

async function capture(page:Page,options:{path:string}){await expect.poll(()=>page.evaluate(()=>{const map=(window as any).__UEC_LOCAL_PREVIEW_MAP__;return Boolean(map&&map.areTilesLoaded()&&map.getLayer('v1-source-pins')&&map.queryRenderedFeatures({layers:['v1-source-pins','approx-reference-pins','approx-reference-points']}).length);}),{timeout:20000}).toBe(true);await page.screenshot(options);}

for(const [width,height] of [[320,812],[390,844]])test(`approved mobile discovery is compact, retains context and never resizes the map at ${width}x${height}`,async({page})=>{
  await page.setViewportSize({width:width!,height:height!});await install(page);await open(page);
  const handle=page.locator('.mobile-sheet-handle');await expect(handle).toHaveAttribute('data-sheet-state','collapsed');await expect(handle.locator('.handle-label')).toHaveText('Search map');
  const stage=await page.locator('.map-stage').boundingBox();await page.locator('.maplibregl-canvas').evaluate(node=>(window as any).__mobileOriginalCanvas=node);
  const camera=()=>page.evaluate(()=>{const m=(window as any).__UEC_LOCAL_PREVIEW_MAP__;return m?[m.getCenter().lng,m.getCenter().lat,m.getZoom(),m.getPitch(),m.getBearing()]:null});const originalCamera=await camera();
  await handle.click();await expect(handle).toHaveAttribute('data-sheet-state','middle');await expect(page.locator('.mobile-results-heading strong')).toHaveText('132 records');
  const query=page.locator('#field-search'),filter=page.locator('.mobile-filter-button'),q=(await page.locator('.query-box').boundingBox())!,f=(await filter.boundingBox())!;expect(q.y).toBeCloseTo(f.y,0);expect(f.height).toBeGreaterThanOrEqual(44);expect(await page.locator('.query-box').evaluate(node=>getComputedStyle(node).borderTopWidth)).toBe('1px');
  await expect(page.locator('.mobile-search-context')).toContainText('Everywhere');const rail=(await page.locator('.results').boundingBox())!;
  await expect(page.locator('.mobile-record-list [data-record-id]')).toHaveCount(100);const firstThree=await page.locator('.mobile-record-list [data-record-id]').evaluateAll(nodes=>nodes.slice(0,3).map(node=>({height:node.getBoundingClientRect().height,bottom:node.getBoundingClientRect().bottom})));expect(firstThree.every(row=>row.height>=44&&row.bottom<=rail.y+rail.height)).toBe(true);
  await expect(page.locator('.mobile-record-list [data-record-id]').first()).toHaveAttribute('aria-label',/Example register/);
  if(process.env.UEC_MOBILE_CAPTURE_DIR)await capture(page,{path:`${process.env.UEC_MOBILE_CAPTURE_DIR}/middle-${width}.png`});
  await page.getByRole('button',{name:'Search this area',exact:true}).click();await expect(page.locator('.mobile-search-context')).toContainText('This map area');await expect(page.locator('.mobile-results-heading strong')).toHaveText('130 records');
  await handle.focus();await page.keyboard.press('Home');await expect(handle).toHaveAttribute('data-sheet-state','collapsed');await expect(handle.locator('.handle-context')).toContainText('This map area');if(process.env.UEC_MOBILE_CAPTURE_DIR)await page.screenshot({path:`${process.env.UEC_MOBILE_CAPTURE_DIR}/collapsed-${width}.png`});
  const grip=(await handle.boundingBox())!;await page.mouse.move(width!/2,grip.y+12);await page.mouse.down();await page.mouse.move(width!/2,height!*0.49,{steps:12});await page.mouse.up();await expect(handle).toHaveAttribute('data-sheet-state','middle');
  await handle.focus();await page.keyboard.press('End');await expect(handle).toHaveAttribute('data-sheet-state','expanded');await expect(handle).toBeInViewport();expect((await handle.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  expect(await camera()).toEqual(originalCamera);
  await page.locator('.list-content').evaluate(node=>{node.scrollTop=170});const scroll=await page.locator('.list-content').evaluate(node=>node.scrollTop);await page.locator('.mobile-record-list [data-record-id]').nth(3).click();await expect(handle).toHaveAttribute('data-sheet-state','expanded');await expect(page.locator('.reading-sheet .detail h1')).toContainText('Synthetic facility');
  const name=await page.locator('.reading-sheet .detail h1 .record-name').textContent();await page.getByRole('button',{name:'Show on map',exact:true}).click();await expect(handle).toHaveAttribute('data-sheet-state','collapsed');await expect(handle.locator('.handle-label')).toHaveText('View details');await expect(handle.locator('.handle-context')).toContainText(name!);
  await handle.click();await expect(handle).toHaveAttribute('data-sheet-state','middle');await page.locator('.back-to-results').click();await expect(page.locator('.list-content')).toBeVisible();expect(await page.locator('.list-content').evaluate(node=>node.scrollTop)).toBeCloseTo(scroll,0);
  expect(await page.locator('.map-stage').boundingBox()).toEqual(stage);expect(await page.locator('.maplibregl-canvas').evaluate(node=>node===(window as any).__mobileOriginalCanvas)).toBe(true);
  // Selection legitimately flies; opening and snapping the unselected sheet did not.
  expect(originalCamera).not.toBeNull();expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await expect(page.getByRole('button',{name:'Language',exact:true})).toBeVisible();
});

test('mobile filter changes are staged, close cancels, Apply batches once and preserves mapped semantics',async({page})=>{
  await page.setViewportSize({width:390,height:844});const calls=await install(page);await open(page);const handle=page.locator('.mobile-sheet-handle');await handle.click();await expect(page.locator('[data-record-id]')).toHaveCount(100);
  const count=()=>calls.filter(call=>call.path==='/api/v2/locations').length;const before=count();await page.locator('.mobile-filter-button').click();const panel=page.locator('.mobile-filter-view');await expect(panel).toBeVisible();await expect(handle).toHaveAttribute('data-sheet-state','expanded');
  await panel.getByRole('checkbox',{name:'Slaughter',exact:true}).check();await panel.getByRole('checkbox',{name:'Exact',exact:true}).check();await page.waitForTimeout(350);expect(count()).toBe(before);
  await page.getByRole('button',{name:'Language',exact:true}).click();await page.keyboard.press('Escape');await expect(panel).toBeVisible();await expect(panel.getByRole('checkbox',{name:'Exact',exact:true})).toBeChecked();
  await panel.getByRole('button',{name:'Back to results',exact:true}).click();await expect(panel).toHaveCount(0);await expect(handle).toHaveAttribute('data-sheet-state','middle');expect(count()).toBe(before);
  await page.locator('.mobile-filter-button').click();await expect(panel.getByRole('checkbox',{name:'Slaughter',exact:true})).not.toBeChecked();await expect(panel.getByRole('checkbox',{name:'Exact',exact:true})).not.toBeChecked();
  await panel.getByRole('checkbox',{name:'Slaughter',exact:true}).check();const mapped=panel.getByRole('checkbox',{name:'Mapped',exact:true});await panel.getByRole('checkbox',{name:'Exact',exact:true}).check();await expect(mapped).toHaveJSProperty('indeterminate',true);await mapped.check();await expect(panel.getByRole('checkbox',{name:'Source-reported',exact:true})).toBeChecked();await expect(panel.getByRole('checkbox',{name:'Approximate',exact:true})).toBeChecked();await panel.getByRole('checkbox',{name:'Unmapped',exact:true}).check();await mapped.uncheck();await expect(panel.getByRole('checkbox',{name:'Unmapped',exact:true})).toBeChecked();await mapped.check();
  if(process.env.UEC_MOBILE_CAPTURE_DIR)await page.screenshot({path:`${process.env.UEC_MOBILE_CAPTURE_DIR}/filters-390.png`});
  const prior=count();await panel.getByRole('button',{name:'Apply filters',exact:true}).click();await expect.poll(count).toBe(prior+1);await expect(page.locator('.mobile-record-list [data-record-id]')).toHaveCount(22);expect(count()).toBe(prior+1);expect(calls.filter(call=>call.path==='/api/v2/locations').at(-1)!.params.category_keys).toBe('slaughter');await expect(page.locator('.mobile-category-chip')).toContainText('Slaughter');
  await handle.focus();await page.keyboard.press('Home');await expect(handle.locator('.handle-context')).toContainText('Slaughter');
});

test('mobile scope settings keep radius and privacy, and list errors retry without removing the map',async({page})=>{
  await page.setViewportSize({width:320,height:812});await page.addInitScript(()=>{(window as any).__geoCalls=0;Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition(success:PositionCallback){(window as any).__geoCalls++;success({coords:{latitude:39.2777,longitude:-94.4333}}as GeolocationPosition)}}});});const calls=await install(page);await open(page);await page.locator('.mobile-sheet-handle').click();expect(await page.evaluate(()=>(window as any).__geoCalls)).toBe(0);
  await page.locator('.mobile-scope-toggle').click();const scope=page.locator('.mobile-scope-menu');await scope.getByRole('button',{name:/Near me/}).click();await expect(page.locator('.mobile-scope-toggle')).toContainText('Near me');expect(await page.evaluate(()=>(window as any).__geoCalls)).toBe(1);expect(page.url()).not.toMatch(/39\.2777|94\.4333/);
  await page.locator('.mobile-scope-toggle').click();await scope.locator('summary').click();await expect(scope.getByRole('slider',{name:'Search radius',exact:true})).toBeVisible();await scope.getByRole('slider',{name:'Search radius',exact:true}).fill('75');await expect.poll(()=>Number(calls.filter(call=>call.path==='/api/v2/locations').at(-1)?.params.radius_km)).toBeCloseTo(120.7008,6);await page.keyboard.press('Escape');
  await page.locator('.mobile-clear-scope').click();await expect(page.locator('.mobile-scope-toggle')).toContainText('Everywhere');expect(page.url()).not.toMatch(/39\.2777|94\.4333/);
  await page.getByRole('navigation',{name:'Primary'}).getByRole('link',{name:'About',exact:true}).click();await expect.poll(()=>new URL(page.url()).hash.startsWith('#/about')).toBe(true);await page.getByRole('navigation',{name:'Primary'}).getByRole('link',{name:'Map',exact:true}).click();await expect(page.locator('.map-navigation')).toBeVisible();expect(await page.evaluate(()=>(window as any).__geoCalls)).toBe(1);
  if(await page.locator('.mobile-sheet-handle').getAttribute('data-sheet-state')==='collapsed')await page.locator('.mobile-sheet-handle').click();await expect(page.locator('#field-search')).toBeVisible();
  await expect(page.locator('.mobile-record-list [data-record-id]')).toHaveCount(100);
  await page.locator('.list-content').evaluate(node=>{node.scrollTop=170});
  let fail=true;let releaseFailure!:()=>void;const failureGate=new Promise<void>(resolve=>releaseFailure=resolve);await page.route('**/api/v2/locations?**',async route=>{if(fail){await failureGate;await route.fulfill({status:502,json:{}});}else await route.fallback();});const canvas=page.locator('.maplibregl-canvas');await canvas.evaluate(node=>(window as any).__retryCanvas=node);await page.locator('#field-search').fill('Synthetic facility 00');
  await expect(page.locator('.mobile-results-heading strong')).toHaveText('Searching · showing previous results');await expect(page.locator('.mobile-results-heading strong')).toBeInViewport();releaseFailure();
  const recovery=page.locator('.search-list-recovery');await expect(recovery).toContainText('Search unavailable · showing previous results');await expect(recovery).toBeInViewport({ratio:1});await expect(recovery.getByRole('button',{name:'Retry',exact:true})).toBeInViewport({ratio:1});await expect(page.locator('.mobile-record-list [data-record-id]')).toHaveCount(100);await expect(page.locator('.search-error')).toHaveCount(1);
  await page.locator('.list-content').evaluate(node=>{node.scrollTop=0});await expect(recovery).toBeInViewport({ratio:1});if(process.env.UEC_MOBILE_CAPTURE_DIR)await page.screenshot({path:process.env.UEC_MOBILE_CAPTURE_DIR+'/retry-visible-320.png'});
  await expect(canvas).toBeVisible();fail=false;await recovery.getByRole('button',{name:'Retry',exact:true}).click();await expect(recovery).toHaveCount(0);expect(await canvas.evaluate(node=>node===(window as any).__retryCanvas)).toBe(true);
  expect(await page.evaluate(()=>JSON.stringify({state:history.state,local:{...localStorage},session:{...sessionStorage}}))).not.toMatch(/39\.2777|94\.4333/);
});


for(const height of [812,568])test('mobile scope settings remain reachable at 320x'+height,async({page})=>{
  await page.setViewportSize({width:320,height});await install(page);await open(page);await page.locator('.mobile-sheet-handle').click();const stage=await page.locator('.map-stage').boundingBox();
  await page.locator('.mobile-scope-toggle').click();const menu=page.locator('.mobile-scope-menu');const everywhere=menu.getByRole('button',{name:'Everywhere',exact:true});await expect(everywhere).toBeInViewport();expect(await everywhere.evaluate(node=>{const rect=node.getBoundingClientRect();return node.contains(document.elementFromPoint(rect.x+rect.width/2,rect.y+rect.height/2));})).toBe(true);await menu.locator('summary').scrollIntoViewIfNeeded();await menu.locator('summary').click();const radius=menu.getByRole('radio',{name:'Radius',exact:true});await radius.scrollIntoViewIfNeeded();await expect(radius).toBeInViewport({ratio:1});await radius.check();
  const slider=menu.getByRole('slider',{name:'Search radius',exact:true});await slider.scrollIntoViewIfNeeded();await expect(slider).toBeInViewport({ratio:.99});const sliderRect=(await slider.boundingBox())!;expect(sliderRect.y).toBeGreaterThanOrEqual(0);expect(sliderRect.y+sliderRect.height).toBeLessThanOrEqual(height);const rect=(await menu.boundingBox())!;expect(rect.y).toBeGreaterThanOrEqual(0);expect(rect.y+rect.height).toBeLessThanOrEqual(height);expect(await menu.evaluate(node=>node.scrollHeight>node.clientHeight)).toBe(true);expect(await menu.evaluate(node=>node.scrollTop)).toBeGreaterThan(0);
  await slider.focus();await page.keyboard.press('ArrowRight');await expect(slider).toHaveValue('55');expect(await page.locator('.map-stage').boundingBox()).toEqual(stage);expect(await page.evaluate(()=>window.scrollY)).toBe(0);if(process.env.UEC_MOBILE_CAPTURE_DIR)await page.screenshot({path:process.env.UEC_MOBILE_CAPTURE_DIR+'/scope-settings-320-'+height+'.png'});
  await page.keyboard.press('Escape');await expect(menu).toHaveCount(0);await expect(page.locator('.mobile-scope-toggle')).toBeFocused();await expect(page.locator('.mobile-sheet-handle')).toHaveAttribute('data-sheet-state','middle');
});
test('desktop retains the existing live filter surface and fixed overlay geometry',async({page})=>{
  await page.setViewportSize({width:1440,height:900});const calls=await install(page);await open(page);const stage=await page.locator('.map-stage').boundingBox();await page.locator('#field-search').click();await page.locator('.filters > summary').click();await page.locator('.filter-sheet').getByRole('checkbox',{name:'Slaughter',exact:true}).check();await expect.poll(()=>calls.filter(call=>call.path==='/api/v2/locations').at(-1)?.params.category_keys).toBe('slaughter');await expect(page.locator('.mobile-filter-view')).toHaveCount(0);expect(await page.locator('.map-stage').boundingBox()).toEqual(stage);if(process.env.UEC_MOBILE_CAPTURE_DIR){await page.locator('.filter-sheet').getByRole('button',{name:'Show results',exact:true}).click();await capture(page,{path:`${process.env.UEC_MOBILE_CAPTURE_DIR}/desktop.png`});}await page.getByRole('button',{name:'Search settings',exact:true}).click();await expect(page.locator('#map-search-settings')).toBeVisible();await page.setViewportSize({width:320,height:812});await expect(page.locator('#map-search-settings')).toHaveCount(0);
});

