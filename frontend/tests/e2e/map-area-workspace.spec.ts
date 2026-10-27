import { expect, test } from '@playwright/test';

test('area apply and clear keep the collapsed workspace, query, filters and fixed map intact',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.route('https://**/*',route=>route.abort());
  const release='synthetic-area-study',id='550e8400-e29b-41d4-a716-446655440000',stamp='2026-10-18T00:00:00Z';
  const identity={profile:'official',release_id:release,manifest_sha256:'a'.repeat(64),suppression_generation:1};
  const meta={profile:'official',release_id:release,ruleset_version:'synthetic-study',release_created_at:stamp};
  const row={facility_id:id,canonical_name:'Synthetic processing record',city:'Synthetic locality',country_code:'DK',category:'processing_and_preparation',source_type:'official',publication_profile:'official',factual_review_status:'reviewed',privacy_screening_status:'passed',project_approval:'approved',reviewer_role:null,publication_warning:null,display_precision:'source_reported',latitude:56.1629,longitude:10.2039,first_observed_at:null,last_observed_at:stamp,observation_count:1,lifecycle_status:'active_observed',provenance_source_id:'synthetic-study',provenance_source:null,provenance_source_name:'Synthetic food register',provenance_source_url:'https://example.test/register',provenance_retrieved_at:stamp,source_rights_status:'cleared',release_id:release,release_ruleset_version:'synthetic-study'};
  const matches:URLSearchParams[]=[];
  await page.route('**/api/v2/**',async route=>{
    const url=new URL(route.request().url());let body:unknown;
    if(url.pathname==='/api/v2/releases/manifest')body={api_version:'v2',data:{...identity,manifest:{}}};
    else if(url.pathname==='/api/v2/locations')body={api_version:'v2',data:[row],meta:{...meta,next_cursor:null,total_count:1}};
    else if(url.pathname.startsWith('/api/v2/locations/'))body={api_version:'v2',data:row,meta};
    else if(url.pathname==='/api/v2/map/feed')body={api_version:'v2',data:{type:'FeatureCollection',features:[{type:'Feature',id,geometry:{type:'Point',coordinates:[row.longitude,row.latitude]},properties:{facility_id:id,source_id:'synthetic-study',category_key:row.category,category_keys:[row.category],precision:'source_reported',weight:1}}]},meta:{...identity,feature_count:1,public_record_count:1,unmapped_count:0,release_label:'Synthetic area study',dataset_version:'synthetic-study'}};
    else if(url.pathname==='/api/v2/map/matches'){matches.push(url.searchParams);body={api_version:'v2',data:{facility_ids:[id]},meta:{...identity,total_count:1,mapped_count:1}}}
    else if(url.pathname==='/api/v2/discovery/facets')body={api_version:'v2',dimensions:{country_code:[{value:'DK',count:1}]},meta:{...meta,coverage_scope:'Synthetic study',count_semantics:'Matching synthetic records',filters:{}}};
    else if(url.pathname.startsWith('/api/v2/graph/'))body={api_version:'v2-graph-v1',data:[],meta:{...meta,limit:20,page_max:100,next_cursor:null,public_projection:true}};
    else return route.fulfill({status:404,json:{}});
    return route.fulfill({json:body});
  });
  await page.goto(`./#/map?list=open&release_id=${release}&category=processing_and_preparation&country=DK&lat=56.1629&lon=10.2039&z=10`);
  await page.locator('#field-search').fill('Synthetic');
  const handle=page.getByRole('button',{name:'Search map',exact:true});
  await handle.focus();await page.keyboard.press('Home');
  const mapBox=await page.locator('.map-stage').boundingBox();
  const area=page.getByRole('button',{name:'Search this area',exact:true});await expect(area).toBeEnabled();
  await area.click();
  const clear=page.getByRole('button',{name:'Clear area search',exact:true});await expect(clear).toBeVisible();
  await expect(handle).toHaveAttribute('data-sheet-state','collapsed');await expect(page.locator('#field-search')).toBeHidden();
  await expect.poll(()=>matches.at(-1)?.has('min_lon')).toBe(true);
  for(const [key,value] of Object.entries({q:'Synthetic',category_keys:'processing_and_preparation',country_code:'DK'}))expect(matches.at(-1)?.get(key)).toBe(value);
  expect(await page.locator('.map-stage').boundingBox()).toEqual(mapBox);
  await handle.click();await expect(page.getByRole('button',{name:'Remove filter',exact:true}).filter({hasText:'This map area'})).toBeVisible();
  await handle.focus();await page.keyboard.press('Home');await clear.click();
  await expect(area).toBeVisible();await expect(handle).toHaveAttribute('data-sheet-state','collapsed');
  await expect.poll(()=>matches.at(-1)?.has('min_lon')).toBe(false);
  for(const [key,value] of Object.entries({q:'Synthetic',category_keys:'processing_and_preparation',country_code:'DK'}))expect(matches.at(-1)?.get(key)).toBe(value);
  expect(await page.locator('.map-stage').boundingBox()).toEqual(mapBox);
  await handle.click();await expect(page.locator('#field-search')).toHaveValue('Synthetic');
  await expect(page.getByRole('button',{name:'Remove filter',exact:true}).filter({hasText:'This map area'})).toHaveCount(0);
  expect(new URL(page.url()).hash).not.toMatch(/Synthetic|min_lon|max_lon|min_lat|max_lat/);
});
