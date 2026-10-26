import { expect, test, type Page } from '@playwright/test';
test('the default public app exposes no local encrypted-inbox routes or SDK requests', async ({ page }) => {
  const secureRequests: string[] = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (/\/community\/secure\/|openpgp|SecureInbox|SecureReview|SecureContributionFlow/.test(url.pathname)) secureRequests.push(url.pathname);
  });
  await page.route('**/api/**', route => route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }));
  for (const route of ['#/secure-inbox', '#/secure-review']) {
    await page.goto(route);
    await expect(page.getByRole('heading', { name: 'Page not found', exact: true })).toBeVisible();
  }
  expect(secureRequests).toEqual([]);
});
const id = '18c6ef3a-28cd-4c8e-a9bb-3951f45f210d';
const recordId = '27d7ef4b-39de-4d9f-bacc-4062f560321e';
const secondId = '38e8af5c-40ef-4e0a-adbd-5173f671432f';
const release = 'synthetic-community-release';
const publicRelease = 'synthetic-public-release';
const claimWarning = 'Unreviewed community claim: not verified by Until Every Cage.';
const secret = 'synthetic-one-time-receipt-secret';
const claimDto = { submission_id:id, kind:'facility', record_id:recordId, release_id:release, public_record_url:`/api/v2/locations/${recordId}?profile=community&release_id=${release}`, origin:'community-submitted', factual_review_status:'unreviewed', project_approval:'not-approved', warning:claimWarning };
const rowDto = { submission_id:id, kind:'facility', status:'received', created_at:'2026-10-01T12:00:00Z', label:'Synthetic facility claim', country_code:'DK', locality:'Sample locality', claimed_activity:'Synthetic activity', source_url:'https://example.test/synthetic-source', observed_on:'2026-09-20', description:'Synthetic queue context', location_text:'Broad synthetic area', claimed_precision:'coarse', location_input_method:'manual_pin', claimed_latitude:55.7, claimed_longitude:12.5, target_record_id:recordId, duplicate_record_id:null, contact_email:'private-synthetic@example.test', receipt_secret_hash:'synthetic-never-render' };
const publicWire = {facility_id:recordId,canonical_name:'Synthetic public facility',city:'Synthetic locality',country_code:'DK',category:'processing_and_preparation',source_type:'official',publication_profile:'official',factual_review_status:'reviewed',privacy_screening_status:'passed',project_approval:'approved',reviewer_role:null,publication_warning:null,display_precision:'unmapped',latitude:null,longitude:null,first_observed_at:null,last_observed_at:'2026-01-01T00:00:00Z',observation_count:1,lifecycle_status:'active_observed',provenance_source_id:'synthetic.source',provenance_source:null,provenance_source_name:'Synthetic public authority',provenance_source_url:'https://example.test/source',provenance_retrieved_at:'2026-01-01T00:00:00Z',source_rights_status:'cleared',release_id:publicRelease,release_ruleset_version:'synthetic-rules'};
async function mockCommunityApi(page: Page) {
  // Every API request is intercepted. No test can reach the configured hosted intake.
  await page.route('**/*', route => { const url=new URL(route.request().url()); return url.protocol.startsWith('http')&&!['127.0.0.1','localhost'].includes(url.hostname) ? route.abort() : route.fallback(); });
  await page.route('**/api/**', async route => {
    const request=route.request(), url=new URL(request.url()), path=url.pathname;
    if (!path.startsWith('/api/')) return route.fallback();
    const json=(body:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(path==='/api/community/capabilities') return json({enabled:true,types:['facility','evidence','correction','duplicate','privacy_removal']});
    if(path==='/api/community/submissions'&&request.method()==='POST') return json({submission_id:id,receipt_secret:secret,status:'received'},201);
    if(path==='/api/community/status'&&request.method()==='POST') return json({submission_id:id,status:'published',public_record_url:claimDto.public_record_url});
    if(path==='/api/private/community/submissions'&&request.method()==='GET') return json({pending_count:1,submissions:[{...rowDto,status:url.searchParams.get('status')==='screened'?'screened':'received'}]});
    if(path.endsWith('/disposition')&&request.method()==='POST') return json({status:'screened'});
    if(path==='/api/v2/releases/manifest') return json({api_version:'v2',data:{profile:'community',release_id:release}});
    if(path==='/api/community/claims') return json({claims:[claimDto],claim_count:1,warning:claimWarning});
    if(path===`/api/community/claims/${id}`) return json(claimDto);
    if(path==='/api/v2/locations') return json({api_version:'v2',data:[publicWire],meta:{profile:'official',release_id:publicRelease,ruleset_version:'synthetic-rules',coverage_note:'Synthetic fixture',next_cursor:null,total_count:1}});
    if(path===`/api/v2/locations/${recordId}`) return json({api_version:'v2',data:publicWire,meta:{profile:'official',release_id:publicRelease,ruleset_version:'synthetic-rules',coverage_note:'Synthetic fixture'}});
    return json({},404);
  });
}
test.beforeEach(async({page})=>mockCommunityApi(page));
const task=(page:Page,name:string)=>page.getByRole('navigation',{name:'Contribution tasks'}).getByRole('link',{name,exact:false});
const subtype=(page:Page,name:string)=>page.getByRole('navigation',{name:'Type of update'}).getByRole('link',{name,exact:true});
async function submitAndTrack(page:Page,bug=false){await page.getByRole('button',{name:bug?'Send report':'Send for review',exact:true}).click();await expect(page.getByRole('heading',{name:'Contribution received',exact:true})).toBeVisible();return page.getByRole('link',{name:bug?'Track report':'Track submission',exact:true});}

test('legacy entry and task switches retain each draft in page memory without loading a map',async({page})=>{
  const pageErrors:string[]=[];page.on('pageerror',error=>pageErrors.push(error.message));
  const map='#/map?lat=44.5&lon=8.1&z=5&basemap=satellite&release_id='+publicRelease;
  await page.goto(`#/contribute/evidence?target=${recordId}&map=${encodeURIComponent(map)}`);
  await expect(page.getByRole('heading',{name:'Add evidence',exact:true})).toBeVisible();
  await expect(page.locator('#intake-target')).toHaveValue(recordId);
  await page.getByLabel('What did you find?').fill('Synthetic retained evidence');
  await subtype(page,'Correction').click();
  await page.getByLabel('What should be corrected?').fill('Synthetic retained correction');
  await task(page,'Add a facility').click();
  await page.getByLabel('Facility name').fill('Synthetic retained facility');
  await expect(page.locator('.pin-map')).toHaveCount(0);
  await task(page,'Report a problem').click();
  await page.getByLabel('What happened?').fill('Synthetic retained bug');
  await task(page,'Update a record').click();
  await subtype(page,'Evidence').click();
  await expect(page.getByLabel('What did you find?')).toHaveValue('Synthetic retained evidence');
  await subtype(page,'Correction').click();
  await expect(page.getByLabel('What should be corrected?')).toHaveValue('Synthetic retained correction');
  await task(page,'Add a facility').click();
  await expect(page.getByLabel('Facility name')).toHaveValue('Synthetic retained facility');
  await task(page,'Report a problem').click();
  await expect(page.getByLabel('What happened?')).toHaveValue('Synthetic retained bug');
  await expect(page.getByRole('link',{name:'Report a public issue on GitHub',exact:true})).toBeVisible();
  const params=new URLSearchParams(new URL(page.url()).hash.split('?')[1]);
  expect(params.get('map')).toBe(map);expect(params.get('target')).toBe(recordId);
  const storage=await page.evaluate(()=>({local:Object.values(localStorage),session:Object.values(sessionStorage)}));
  expect(JSON.stringify(storage)).not.toContain('Synthetic retained');expect(pageErrors).toEqual([]);
});

test('optional location opens only on request, supports map fallback and preserves points between tasks',async({page})=>{
  await page.addInitScript(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type:string,...args:unknown[]){if(['webgl','webgl2','experimental-webgl'].includes(type))return null;return original.call(this,type,...(args as []));} as typeof HTMLCanvasElement.prototype.getContext;});
  let submitted:Record<string,unknown>|undefined;
  await page.route('**/api/community/submissions',async route=>{submitted=route.request().postDataJSON();await route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({submission_id:id,receipt_secret:secret,status:'received'})});});
  await page.goto('#/contribute');
  await expect(page.locator('.pin-map')).toHaveCount(0);
  await page.getByText('Add location details (optional)',{exact:true}).click();
  await expect(page.getByText('The map could not be opened. You can enter coordinates below instead.')).toBeVisible();
  await page.getByLabel('Latitude',{exact:true}).fill('55.7');await page.getByLabel('Longitude',{exact:true}).fill('12.5');
  await task(page,'Update a record').click();await task(page,'Add a facility').click();
  await expect(page.getByLabel('Latitude',{exact:true})).toHaveValue('55.7');
  await page.getByLabel('Facility name').fill('Synthetic fallback facility');
  await page.getByLabel('Country (optional)').selectOption('DK');await page.getByLabel('Locality (optional)').fill('Synthetic town');
  await page.getByLabel(/I have permission/).check();await submitAndTrack(page);
  expect(submitted).toMatchObject({claimed_latitude:55.7,claimed_longitude:12.5,location_input_method:'text',country_code:'DK',locality:'Synthetic town'});
});

test('bounded public search uses the chosen release and a valid paste remains usable when details are missing',async({page})=>{
  const searches:URL[]=[];
  page.on('request',r=>{const url=new URL(r.url());if(url.pathname==='/api/v2/locations')searches.push(url);});
  await page.goto(`#/contribute/correction?map=${encodeURIComponent('#/map?release_id='+publicRelease)}`);
  await page.getByPlaceholder('Search a facility or paste its link').fill('Syn');
  await page.getByPlaceholder('Search a facility or paste its link').fill('Synthetic');
  await page.getByRole('list',{name:'Matching facilities'}).getByRole('button').click();
  await expect(page.locator('#intake-target')).toHaveValue(recordId);
  expect(searches.length).toBe(1);expect(searches[0]!.searchParams.get('limit')).toBe('5');expect(searches[0]!.searchParams.get('release_id')).toBe(publicRelease);
  await task(page,'Privacy / removal').click();
  await page.locator('#intake-target').fill(`https://example.test/#/records/${secondId}`);
  await expect(page.getByText('Record link ready. Public details are unavailable.',{exact:true})).toBeVisible();
  await page.getByLabel('What should we review?').fill('Synthetic private request');await page.getByLabel(/I have permission/).check();
  await submitAndTrack(page);
});

for(const kind of ['facility','evidence','correction','duplicate','privacy_removal','bug'] as const)test(`${kind} submits its supported payload and returns a private receipt`,async({page})=>{
  let submitted:Record<string,unknown>|undefined;const urls:string[]=[];
  page.on('request',r=>urls.push(r.url()+' '+(r.headers().referer??'')));
  await page.route('**/api/community/submissions',async route=>{submitted=route.request().postDataJSON();await route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({submission_id:id,receipt_secret:secret,status:'received'})});});
  await page.goto(`#/contribute?type=${kind}`);
  if(kind==='facility'){await page.getByLabel('Facility name').fill('Synthetic name only');await page.getByText('Additional details (optional)',{exact:true}).click();await page.getByLabel('Primary activity (optional)').selectOption('slaughter');}
  else if(kind==='bug'){await page.getByLabel('What happened?').fill('Synthetic issue');await page.getByLabel('Steps to reproduce').fill('Synthetic steps');await page.getByText('Additional details (optional)',{exact:true}).click();await page.getByLabel('What did you expect?').fill('Synthetic expectation');await page.getByLabel('Page link (optional)').fill('https://example.test/issue');}
  else {await page.locator('#intake-target').fill(`#/records/${recordId}`);if(kind==='duplicate')await page.locator('#intake-duplicate').fill(`#/records/${secondId}`);else if(kind==='evidence')await page.getByLabel('Source link (optional)').fill('https://example.test/evidence');else await page.getByLabel(kind==='correction'?'What should be corrected?':'What should we review?').fill('Synthetic explanation');}
  if(kind!=='bug')await page.getByLabel(/I have permission/).check();
  const tracking=await submitAndTrack(page,kind==='bug');
  expect(submitted).toMatchObject({kind,consent:true});
  if(kind==='facility'){expect(submitted).toMatchObject({claimed_precision:'unknown',claimed_activity:'slaughter'});expect(submitted).not.toHaveProperty('claimed_latitude');}
  if(kind==='duplicate')expect(submitted?.duplicate_record_id).toBe(secondId);
  if(kind==='bug')expect(submitted).toMatchObject({description:'Synthetic issue',reproduction_steps:'Synthetic steps',expected_behavior:'Synthetic expectation',page_url:'https://example.test/issue'});
  await expect(tracking).toHaveAttribute('href',`#/contribution-status?submission_id=${id}&receipt_secret=${secret}`);
  expect(page.url()).not.toContain(secret);expect(urls.some(url=>url.includes(secret))).toBe(false);
});

test('validation stays inline and unsuccessful submissions preserve entered fields',async({page})=>{
  let writes=0;
  await page.route('**/api/community/submissions',async route=>{writes++;await route.fulfill({status:429,contentType:'application/json',body:'{}'});});
  await page.goto('#/contribute');await page.getByRole('button',{name:'Send for review',exact:true}).click();
  await expect(page.getByLabel('Facility name')).toBeFocused();expect(writes).toBe(0);
  await page.getByLabel('Facility name').fill('Synthetic retained after failure');await page.getByLabel(/I have permission/).check();
  await page.getByRole('button',{name:'Send for review',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('temporarily at capacity');
  await expect(page.getByLabel('Facility name')).toHaveValue('Synthetic retained after failure');expect(writes).toBe(1);
});

test('receipt copying reports success/failure and tracking credentials stay in fragment and POST body',async({page})=>{
  await page.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw new Error('Synthetic denial');}}}));
  const requests:Array<{url:string;referer:string|undefined}>=[];let statusBody:unknown;
  page.on('request',r=>requests.push({url:r.url(),referer:r.headers().referer}));
  await page.route('**/api/community/status',async route=>{statusBody=route.request().postDataJSON();await route.fulfill({contentType:'application/json',body:JSON.stringify({submission_id:id,status:'screened'})});});
  await page.goto('#/contribute');await page.getByLabel('Facility name').fill('Synthetic receipt');await page.getByLabel(/I have permission/).check();
  const tracker=await submitAndTrack(page);await page.getByRole('button',{name:'Copy tracking link',exact:true}).click();await expect(page.getByRole('alert')).toContainText('could not be copied');
  await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{}}}));
  await page.getByRole('button',{name:'Copy tracking link',exact:true}).click();await expect(page.getByRole('button',{name:'Copied',exact:true})).toBeVisible();
  await tracker.click();await expect(page.getByRole('heading',{name:'Privacy screened',exact:true})).toBeVisible();
  await expect(page.getByText('Privacy screening is complete. This does not verify the facts or approve publication.',{exact:true})).toBeVisible();
  expect(statusBody).toEqual({submission_id:id,receipt_secret:secret});expect(new URL(page.url()).search).toBe('');
  expect(requests.some(r=>r.url.includes(secret)||r.referer?.includes(secret))).toBe(false);
});

test('status handles all real states and invalid/expired receipts without fabricated decisions or dates',async({page})=>{
  let state='received',invalid=false;
  await page.route('**/api/community/status',route=>route.fulfill({status:invalid?404:200,contentType:'application/json',body:JSON.stringify(invalid?{}:{submission_id:id,status:state})}));
  await page.goto(`#/contribution-status?submission_id=${id}&receipt_secret=${secret}`);
  for(const [status,label] of [['received','Received'],['held','Awaiting review'],['screened','Privacy screened'],['rejected','Not accepted'],['restricted','Restricted'],['removed','Removed from intake'],['published','Published to community submissions']]){
    state=status!;if(status!=='received')await page.getByRole('button',{name:'Refresh status',exact:true}).click();
    await expect(page.locator('.status-result').getByRole('heading',{name:label,exact:true})).toBeVisible();
  }
  await expect(page.getByText('No public link is currently available.',{exact:true})).toBeVisible();
  invalid=true;await page.getByRole('button',{name:'Refresh status',exact:true}).click();await expect(page.getByRole('alert')).toContainText('No active submission matches');
  await expect(page.getByRole('button',{name:'Check status',exact:true})).toBeVisible();
});

test('task, status and receipt layouts fit desktop/mobile in both themes',async({page})=>{
  for(const width of [1024,390,320])for(const theme of ['dark','light']){
    await page.setViewportSize({width,height:844});await page.goto('#/contribute');
    await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
    for(const name of ['Add a facility','Update a record','Report a problem','Privacy / removal']){await task(page,name).click();await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
    await page.goto(`#/contribution-status?submission_id=${id}&receipt_secret=${secret}`);await expect(page.locator('.status-result')).toBeVisible();await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
});test('the operator queue shows structured private context but never contact or receipt fields', async ({ page }) => {
  await page.goto('#/contribution-review');
  await expect(page.getByText(/Private intake warning/)).toBeVisible();
  await page.getByLabel('Local operator token').fill('synthetic-operator-token');
  await page.getByRole('button', { name: 'Open restricted queue' }).click();
  for (const value of ['Synthetic facility claim', 'Denmark', 'Sample locality', 'Synthetic activity', '2026-09-20', 'Broad synthetic area', 'coarse', 'map pin', 'Synthetic queue context']) {
    await expect(page.getByText(value, { exact: false })).toBeVisible();
  }
  await expect(page.getByText('private-synthetic@example.test')).toHaveCount(0);
  await expect(page.getByText('synthetic-never-render')).toHaveCount(0);
  await expect(page.getByText(/Link to an existing community release record/)).toHaveCount(0);
  await page.getByRole('button', { name: 'Privacy screen only' }).click();
  await page.getByLabel('Status filter').selectOption('screened');
  await page.getByRole('button', { name: 'Refresh queue' }).click();
  await expect(page.getByText(/Link to an existing community release record/)).toBeVisible();
  await expect(page.getByText(/does not verify facts or approve a curated release/)).toBeVisible();
});

test('community claims are opt-in, scoped to the current profile, and prominently warned', async ({ page }) => {
  await page.goto('#/community');
  const profileWarning = page.locator('.community-page > .review-warning strong');
  await expect(profileWarning).toHaveText(claimWarning);
  await expect(profileWarning).toBeVisible();
  await expect(page.getByText('1 published submissions · separate profile count')).toBeVisible();
  await page.locator('.claim-row').click();
  await expect(page.getByRole('heading', { name: 'Community claim' })).toBeVisible();
  const claimPageWarning = page.locator('.community-page > .review-warning strong');
  await expect(claimPageWarning).toHaveText(claimWarning);
  await expect(claimPageWarning).toBeVisible();
  await page.getByRole('button', { name: 'Load this claim' }).click();
  await expect(page.getByRole('link', { name: 'View released record data (JSON)' })).toBeVisible();
  await expect(page.locator('.claim-detail').getByText(claimWarning, { exact: true })).toBeVisible();
});


