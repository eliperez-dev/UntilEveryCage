import { expect, test, type Page } from '@playwright/test';
const release='synthetic-integrated-tools';
const stamp='2026-10-18T00:00:00Z';
const rows=[['Synthetic Northbank','processing_and_preparation','US','source_reported',39.2,-94.5],['Synthetic Meadow','animal_keeping_and_production','DE','approximate',40,-95],['Synthetic Unmapped','processing_and_preparation','US','unmapped',null,null]].map(([name,category,country,precision,lat,lon],i)=>({facility_id:`550e8400-e29b-41d4-a716-44665544000${i}`,canonical_name:name,category,country_code:country,city:'Sample town',display_precision:precision,latitude:lat,longitude:lon,source_type:'official',publication_profile:'official',factual_review_status:'reviewed',privacy_screening_status:'passed',project_approval:'approved',reviewer_role:null,publication_warning:null,first_observed_at:null,last_observed_at:stamp,observation_count:1,lifecycle_status:'active_observed',provenance_source_id:'synthetic-source',provenance_source:null,provenance_source_name:'Example register',provenance_source_url:'https://example.test/register',provenance_retrieved_at:stamp,source_rights_status:'cleared',release_id:release,release_ruleset_version:'synthetic-rules',taxonomy_display_category:category,taxonomy_primary_categories:[category],taxonomy_leaf_activities:[],taxonomy_assignments:[]}));
async function install(page:Page){
  await page.route('https://**/*',r=>r.abort());
  const identity={profile:'official',release_id:release,manifest_sha256:'a'.repeat(64),suppression_generation:1};
  const meta={profile:'official',release_id:release,ruleset_version:'synthetic-rules',release_created_at:stamp};
  const calls:URL[]=[];
  await page.route('**/api/v2/**',route=>{
    const url=new URL(route.request().url()),p=url.pathname;calls.push(url);
    const filtered=rows.filter(r=>(!url.searchParams.has('q')||String(r.canonical_name).toLowerCase().includes(url.searchParams.get('q')!.toLowerCase()))&&(!url.searchParams.has('country_code')||url.searchParams.get('country_code')!.split(',').includes(String(r.country_code)))&&(!url.searchParams.has('category_keys')||url.searchParams.get('category_keys')!.split(',').includes(String(r.category)))&&(!url.searchParams.has('display_precision')||url.searchParams.get('display_precision')!.split(',').includes(String(r.display_precision))));
    let body:unknown;
    if(p==='/api/v2/releases/manifest')body={api_version:'v2',data:{...identity,manifest:{}}};
    else if(p==='/api/v2/locations')body={api_version:'v2',data:filtered,meta:{...meta,total_count:filtered.length,next_cursor:null,coverage_note:'Synthetic interface checks.'}};
    else if(p.startsWith('/api/v2/locations/'))body={api_version:'v2',data:rows.find(r=>r.facility_id===p.split('/').pop()),meta};
    else if(p==='/api/v2/map/feed')body={api_version:'v2',data:{type:'FeatureCollection',features:rows.filter(r=>r.latitude!==null).map(r=>({type:'Feature',id:r.facility_id,geometry:{type:'Point',coordinates:[r.longitude,r.latitude]},properties:{facility_id:r.facility_id,source_id:'synthetic-source',category_key:r.category,category_keys:[r.category],precision:r.display_precision,weight:1}}))},meta:{...identity,feature_count:2,public_record_count:3,unmapped_count:1,release_label:'Synthetic tools fixture',dataset_version:'synthetic'}};
    else if(p==='/api/v2/map/matches')body={api_version:'v2',data:{facility_ids:filtered.filter(r=>r.latitude!==null).map(r=>r.facility_id)},meta:{...identity,total_count:filtered.length,mapped_count:filtered.filter(r=>r.latitude!==null).length}};
    else if(p==='/api/v2/discovery/facets')body={api_version:'v2',dimensions:{country_code:[{value:'US',count:2},{value:'DE',count:1}],source_id:[{value:'synthetic-source',label:'Example register',count:3}]},meta:{...meta,filters:{},coverage_scope:'Synthetic checks',count_semantics:'Matching synthetic records'}};
    else if(p.startsWith('/api/v2/graph/'))body={api_version:'v2-graph-v1',data:[],meta:{...meta,limit:20,page_max:100,next_cursor:null,public_projection:true}};
    else return route.fulfill({status:404,json:{}});
    return route.fulfill({json:body});
  });return calls;
}
async function open(page:Page){await page.goto(`./#/map?release_id=${release}&list=closed&lat=39.2&lon=-94.5&z=5`);await expect(page.locator('.maplibregl-canvas')).toBeVisible({timeout:15_000});}

test('desktop search stays anchored, shares its surface with results, and never resizes the canvas',async({page})=>{
  await page.setViewportSize({width:1440,height:900});await install(page);await open(page);
  const input=page.locator('#field-search'),before=await input.boundingBox(),canvas=await page.locator('.map-stage').boundingBox();
  await page.locator('.maplibregl-canvas').evaluate(el=>{(window as any).__originalToolsCanvas=el});await input.click();
  await expect(page.locator('[data-record-id]')).toHaveCount(3);expect(await input.boundingBox()).toEqual(before);expect(await page.locator('.map-stage').boundingBox()).toEqual(canvas);
  const rail=(await page.locator('.results').boundingBox())!,toolbar=(await page.locator('.map-toolbar').boundingBox())!;expect(toolbar.x).toBeCloseTo(24,0);expect(rail.x).toBeCloseTo(toolbar.x,0);expect(rail.y).toBeCloseTo(toolbar.y+toolbar.height-1,0);expect(rail.width).toBeCloseTo(toolbar.width,0);expect(rail.width).toBeCloseTo(480,0);
  await expect(input).toHaveCount(1);await page.getByRole('button',{name:'Close workspace',exact:true}).click();expect(await input.boundingBox()).toEqual(before);
  expect(await page.locator('.maplibregl-canvas').evaluate(el=>el===(window as any).__originalToolsCanvas)).toBe(true);
});

test('desktop toolbar and entire dropdown resize together while narrow layouts and camera remain stable',async({page})=>{
  await page.setViewportSize({width:1440,height:900});await install(page);await open(page);await page.locator('#field-search').click();
  const canvas=await page.locator('.map-stage').boundingBox(),input=page.locator('#field-search'),inputNode=await input.elementHandle();
  const resize=page.getByRole('button',{name:'Resize search panel',exact:true});await resize.focus();await page.keyboard.press('ArrowRight');
  let toolbar=(await page.locator('.map-toolbar').boundingBox())!,panel=(await page.locator('.results').boundingBox())!;expect(toolbar.width).toBeCloseTo(504,0);expect(panel.width).toBeCloseTo(toolbar.width,0);expect(panel.x).toBe(toolbar.x);
  const grip=(await resize.boundingBox())!;await page.mouse.move(grip.x+grip.width/2,grip.y+grip.height/2);await page.mouse.down();await page.mouse.move(grip.x+grip.width/2+80,grip.y+grip.height/2,{steps:6});await page.mouse.up();
  toolbar=(await page.locator('.map-toolbar').boundingBox())!;panel=(await page.locator('.results').boundingBox())!;expect(toolbar.width).toBeCloseTo(584,0);expect(panel.width).toBeCloseTo(toolbar.width,0);expect(await page.locator('.map-stage').boundingBox()).toEqual(canvas);expect(await input.evaluate((node,original)=>node===original,inputNode)).toBe(true);
  for(const width of [641,768]){await page.setViewportSize({width,height:800});toolbar=(await page.locator('.map-toolbar').boundingBox())!;panel=(await page.locator('.results').boundingBox())!;expect(toolbar.x).toBeCloseTo(24,0);expect(toolbar.x+toolbar.width).toBeLessThanOrEqual(width-23);expect(panel.width).toBeCloseTo(toolbar.width,0);expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);}
});

test('one style switch serves desktop and mobile, and area scope clears without extra indicator or opening search',async({page})=>{
  await page.setViewportSize({width:1440,height:900});await install(page);
  const tile=await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=canvas.height=256;canvas.getContext('2d')!.fillRect(0,0,256,256);return canvas.toDataURL('image/png').split(',')[1]!});
  const raster=(route:import('@playwright/test').Route)=>route.fulfill({status:200,contentType:'image/png',body:Buffer.from(tile,'base64')});await page.route('**/World_Imagery/**',raster);await page.route('https://tile.openstreetmap.org/**',raster);await open(page);
  const style=page.getByRole('switch',{name:'Map style: Street',exact:true});await expect(style).toBeEnabled();await expect(style).toHaveAttribute('aria-checked','false');await expect(style).toHaveAttribute('title','Street → Satellite');await expect(page.locator('.style-options button')).toHaveCount(1);await style.focus();await page.keyboard.press('Space');
  await expect(page.getByRole('switch',{name:'Map style: Satellite',exact:true})).toHaveAttribute('aria-checked','true');
  await expect.poll(()=>page.evaluate(()=>(window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0])).toContain('World_Imagery');
  await page.getByRole('switch',{name:'Map style: Satellite',exact:true}).click();await expect(style).toHaveAttribute('aria-checked','false');
  await expect.poll(()=>page.evaluate(()=>(window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0])).toContain('tile.openstreetmap.org');
  const area=page.getByRole('button',{name:'Search this area',exact:true});await expect(area).toBeEnabled();await area.click();await expect(page.locator('.results')).toBeHidden();await expect(page.locator('.area-indicator')).toHaveCount(0);await expect(page.getByText('Searching this area',{exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'Clear area search',exact:true})).toHaveClass(/active/);
  await page.locator('#field-search').click();await expect(page.locator('.filter-chips')).toContainText('This map area');await page.getByRole('button',{name:'Close workspace',exact:true}).click();await page.getByRole('button',{name:'Clear area search',exact:true}).click();await expect(area).toBeVisible();await expect(page.locator('.results')).toBeHidden();
  await page.setViewportSize({width:320,height:844});await expect(style).toBeVisible();await expect(page.locator('.style-options button')).toHaveCount(1);await expect(page.locator('.mobile-sheet-handle')).toHaveAttribute('data-sheet-state','collapsed');const bounds=(await style.boundingBox())!;expect(bounds.height).toBeGreaterThanOrEqual(44);
});

test('compact filters preserve multi-selection, Mapped uses existing precisions, and the footer docks to the panel',async({page})=>{
  await page.setViewportSize({width:1440,height:900});const calls=await install(page);await open(page);await page.locator('#field-search').click();await page.locator('.filters > summary').click();
  const panel=page.locator('.filter-sheet');await expect(panel.getByRole('checkbox',{name:'Processing',exact:true})).toBeVisible();await expect(panel.getByRole('checkbox',{name:'Unclassified',exact:true})).toBeVisible();
  await panel.getByRole('checkbox',{name:'Source-reported',exact:true}).check();await expect(panel.getByRole('checkbox',{name:'Mapped',exact:true})).toHaveJSProperty('indeterminate',true);
  await panel.getByRole('checkbox',{name:'Mapped',exact:true}).check();await expect(panel.getByRole('checkbox',{name:'Mapped',exact:true})).toBeChecked();
  await expect.poll(()=>calls.filter(u=>u.pathname==='/api/v2/locations').at(-1)?.searchParams.get('display_precision')?.split(',').sort()).toEqual(['approximate','exact','source_reported']);
  await panel.getByRole('button',{name:'Clear filters',exact:true}).click();
  await panel.locator('.filter-choice > summary').filter({hasText:'Country'}).click();await panel.getByRole('checkbox',{name:/United States/}).check();await panel.getByRole('checkbox',{name:/Germany/}).check();
  await expect(panel.locator('.filter-choice > summary').filter({hasText:'Country'})).toContainText('United States, Germany');
  const bottom=(await panel.boundingBox())!,rail=(await page.locator('.results').boundingBox())!;expect(bottom.y+bottom.height).toBeCloseTo(rail.y+rail.height,0);
  await expect(panel.getByRole('button',{name:'Show results',exact:true})).toBeInViewport();await panel.getByRole('button',{name:'Show results',exact:true}).click();await expect(panel).toBeHidden();
});

for(const width of [320,390])test(`mobile tools and three sheet positions keep selection and physical drags at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:844});await install(page);await open(page);const handle=page.locator('.mobile-sheet-handle');
  await expect(page.locator('#field-search')).toBeHidden();await expect(handle).toHaveAttribute('data-sheet-state','collapsed');
  const toolbar=(await page.locator('.map-toolbar').boundingBox())!;expect(toolbar.x+toolbar.width/2).toBeCloseTo(width/2,0);
  for(const button of await page.locator('.map-navigation .navigation-stack button:visible').all()){const box=(await button.boundingBox())!;expect(box.width).toBeGreaterThanOrEqual(44);expect(box.height).toBeGreaterThanOrEqual(44)}
  const canvas=await page.locator('.map-stage').boundingBox();await handle.click();await handle.focus();await page.keyboard.press('End');await page.locator('[data-record-id]').first().click();await expect(handle).toHaveAttribute('data-sheet-state','expanded');await expect(page.locator('.show-on-map svg')).toBeVisible();
  const grip=(await handle.boundingBox())!;await page.mouse.move(width/2,grip.y+9);await page.mouse.down();await page.mouse.move(width/2,825,{steps:12});await page.mouse.up();await expect(handle).toHaveAttribute('data-sheet-state','collapsed');
  expect(await page.locator('.map-stage').boundingBox()).toEqual(canvas);await handle.click();await expect(handle).toHaveAttribute('data-sheet-state','middle');expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});
