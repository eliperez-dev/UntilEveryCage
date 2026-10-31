import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
const zh: Record<string,string> = JSON.parse(readFileSync(new URL('../../src/app/locales/zh-Hans.json',import.meta.url),'utf8'));

const release = 'synthetic-chinese-ui';
const id = '550e8400-e29b-41d4-a716-446655440000';
const identity = { profile:'official', release_id:release, manifest_sha256:'a'.repeat(64), suppression_generation:1 };
const meta = { profile:'official', release_id:release, ruleset_version:'synthetic-rules', release_created_at:'2026-01-01T00:00:00Z' };
const row = { facility_id:id, canonical_name:'Synthetic Original Facility Name', country_code:'DK', city:'Sample town', category:'processing_and_preparation', taxonomy_display_category:'processing_and_preparation', taxonomy_primary_categories:['processing_and_preparation'], publication_profile:'official', factual_review_status:'reviewed', privacy_screening_status:'passed', project_approval:'approved', reviewer_role:null, publication_warning:null, display_precision:'source_reported', latitude:45, longitude:5, first_observed_at:null, last_observed_at:'2026-01-01T00:00:00Z', observation_count:1, lifecycle_status:'status_unknown', source_type:'official', source_rights_status:'cleared', provenance_source:null, release_id:release, release_ruleset_version:'synthetic-rules', provenance_source_id:'synthetic-source', provenance_source_name:'Synthetic Original Source', provenance_source_url:'https://example.test/source', provenance_retrieved_at:'2026-01-01T00:00:00Z' };
async function setup(page: Page) {
  let submissions=0;
  await page.route('https://**/*', route=>route.abort());
  await page.route('**/api/**', route=>{
    const path=new URL(route.request().url()).pathname;
    if(!path.startsWith('/api/'))return route.fallback();
    if(path==='/api/community/capabilities') return route.fulfill({json:{enabled:true,types:['facility','evidence','correction','duplicate','privacy_removal']}});
    if(path==='/api/community/submissions'){submissions++;return route.fulfill({status:500,json:{}});}
    if(path==='/api/v2/releases/manifest')return route.fulfill({json:{api_version:'v2',data:{...identity,manifest:{}}}});
    if(path==='/api/v2/discovery/facets')return route.fulfill({json:{api_version:'v2',meta:{...meta,coverage_scope:'Synthetic records',count_semantics:'Synthetic records',filters:{}},dimensions:{country_code:[{value:'DK',count:1}],source_id:[{value:'synthetic-source',label:'Synthetic Original Source',count:1}],category:[{value:'processing_and_preparation',count:1}],display_precision:[{value:'source_reported',count:1}]}}});
    if(path==='/api/v2/map/feed')return route.fulfill({json:{api_version:'v2',data:{type:'FeatureCollection',features:[{type:'Feature',id,geometry:{type:'Point',coordinates:[5,45]},properties:{facility_id:id,source_id:'synthetic-source',country_code:'DK',category_key:'processing_and_preparation',category_keys:['processing_and_preparation'],precision:'source_reported',weight:1}}]},meta:{...identity,feature_count:1,public_record_count:1,unmapped_count:0,release_label:'Synthetic release',dataset_version:'synthetic'}}});
    if(path==='/api/v2/locations')return route.fulfill({json:{api_version:'v2',data:[row],meta:{...meta,total_count:1,next_cursor:null,coverage_note:'Synthetic UI test.'}}});
    if(path===`/api/v2/locations/${id}`)return route.fulfill({json:{api_version:'v2',data:{...row,processing_activities:{raw_non_intact_pork_processing:true,rte_chicken_processing:true}},meta}});
    if(path==='/api/v2/map/matches')return route.fulfill({json:{api_version:'v2',data:{facility_ids:[id]},meta:{...identity,total_count:1,mapped_count:1}}});
    return route.fulfill({status:404,json:{}});
  });
  return ()=>submissions;
}
async function chinese(page:Page){
  await page.locator('.language-action').click();
  await page.locator('#shared-language-menu button[lang="zh-Hans"]').click();
  await expect(page.locator('html')).toHaveAttribute('lang','zh-Hans');
}

test('Chinese persists across pages and reload, with readable phone forms',async({page},info)=>{
  await page.setViewportSize({width:320,height:760});
  const submissions=await setup(page);await page.goto('./');await chinese(page);
  await expect(page.locator('.hero h1')).toContainText(zh['HIDDEN IN']);
  await page.reload();await expect(page.locator('html')).toHaveAttribute('lang','zh-Hans');
  await page.locator('.masthead nav').getByRole('link',{name:zh.About,exact:true}).click();
  await expect(page.getByRole('heading',{name:zh['How the data reaches the map'],exact:true})).toBeVisible();
  await page.locator('.masthead nav').getByRole('link',{name:zh.Contribute,exact:true}).click();
  await page.getByLabel(zh['Facility name'],{exact:false}).fill('Synthetic draft');
  await expect(page.locator('#contribution-task')).toBeVisible();
  await page.locator('#contribution-task').selectOption('privacy_removal');
  await expect(page.locator('main h2')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(submissions()).toBe(0);
  await page.screenshot({path:info.outputPath('chinese-mobile-form.png')});
});

test('Chinese switching preserves map camera, release, query and selected source record',async({page},info)=>{
  await page.setViewportSize({width:1280,height:800});await setup(page);
  await page.goto(`./#/map?release_id=${release}&selected=${id}&list=open&lat=45&lon=5&z=12`);
  await expect(page.locator('.reading-sheet').getByRole('heading',{name:row.canonical_name,exact:false})).toBeVisible();
  await page.waitForFunction(()=>{const map=(window as any).__UEC_LOCAL_PREVIEW_MAP__;return map&&!map.isMoving();});
  const route=page.url(),before=await page.evaluate(()=>{const m=(window as any).__UEC_LOCAL_PREVIEW_MAP__;return[m.getCenter().toArray(),m.getZoom(),m.getPitch(),m.getBearing()];});
  await chinese(page);
  expect(page.url()).toBe(route);
  expect(await page.evaluate(()=>{const m=(window as any).__UEC_LOCAL_PREVIEW_MAP__;return[m.getCenter().toArray(),m.getZoom(),m.getPitch(),m.getBearing()];})).toEqual(before);
  await expect(page.locator('.reading-sheet')).toContainText(zh['Source-provided coordinates']);
  await expect(page.locator('.reading-sheet')).toContainText(row.canonical_name);
  await expect(page.locator('.reading-sheet')).toContainText(row.provenance_source_name);
  await expect(page.locator('.reading-sheet')).toContainText('来源列出了猪肉和鸡肉的加工活动。');
  await expect(page.locator('.reading-sheet .record-id')).toContainText(zh['Record ID']);
  await page.getByRole('button',{name:zh['Back to results'],exact:false}).click();
  await page.locator('#field-search').fill('Synthetic');
  await page.locator('details summary').filter({hasText:zh.Filters}).first().click();
  await expect(page.locator('.results').getByText(zh['Activity category'],{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath('chinese-map-filters.png')});
});
