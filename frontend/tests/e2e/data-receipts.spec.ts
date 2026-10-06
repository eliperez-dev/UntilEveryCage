import { expect, test, type Page } from '@playwright/test';
const id = '18c6ef3a-28cd-4c8e-a9bb-3951f45f210d';
const second = '27d7ef4b-39de-4d9f-bacc-4062f560321e';
const email = 'synthetic-followup@example.test';
const secret = 'synthetic-private-receipt';
const publicWire = {facility_id:id,canonical_name:'Synthetic public record',city:'Synthetic locality',country_code:'DK',category:'Synthetic activity',source_type:'official',publication_profile:'official',factual_review_status:'reviewed',privacy_screening_status:'passed',project_approval:'approved',reviewer_role:null,publication_warning:null,display_precision:'unmapped',latitude:null,longitude:null,first_observed_at:null,last_observed_at:'2026-01-01T00:00:00Z',observation_count:1,lifecycle_status:'active_observed',provenance_source_id:'synthetic.source',provenance_source:null,provenance_source_name:'Synthetic public authority',provenance_source_url:'https://example.test/source',provenance_retrieved_at:'2026-01-01T00:00:00Z',source_rights_status:'cleared',release_id:'synthetic-release',release_ruleset_version:'synthetic-rules'};
async function isolate(page: Page, publicShell = false) {
  await page.route('**/*', route => { const url = new URL(route.request().url()); return url.protocol.startsWith('http') && !['localhost','127.0.0.1'].includes(url.hostname) ? route.abort() : route.fallback(); });
  await page.route('**/api/**', route => new URL(route.request().url()).pathname.startsWith('/api/') ? route.fulfill({ contentType: 'application/json', body: JSON.stringify({ api_version:'v2', data:[], meta:{ release_id:null, profile:'official', coverage_note:'No public release.' } }) }) : route.fallback());
  await page.route('**/dev/real-preview/**', route => route.fulfill({ contentType:'application/json', body:JSON.stringify({ api_version:'real-preview-v1', data:[], meta:{private_preview:true,next_cursor:null} }) }));
  if (publicShell) await page.route('**/v2-preview/', async route => { const response = await route.fetch(); await route.fulfill({ response, body:(await response.text()).replace(/<meta name="uec-local-data-mode" content="real-preview">/g,'') }); });
}
const candidate = (candidate_id = id) => ({ candidate_id, source_id:'synthetic.source', location_class:'unmapped_private_observation', display_precision:'city_postal_coarse', country_code:'DK', city:'Synthetic locality', postal_code:null, latitude:null, longitude:null, coordinate_precision:null, coordinate_review_status:'pending_human_privacy_review', factual_review_status:'not_reviewed', privacy_screening_status:'pending', project_approval:false, publication_status:'not_published', preview_label:'Private development preview — not publication-approved', display_name:candidate_id === id ? 'Synthetic first record' : 'Synthetic next record', activity_label:'Synthetic activity', source_name:'Synthetic authority' });

test('Database and About menus expose their destinations with keyboard and preserve context', async ({ page }) => {
  await isolate(page); await page.goto('./#/about?map=%23%2Fmap%3Ff1a%3Dfield');
  await expect(page.getByRole('button',{name:'Account menu'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Tools',exact:true})).toHaveCount(0);
  const database = page.getByRole('button',{name:'Database',exact:true});
  await database.focus(); await page.keyboard.press('ArrowDown');
  await expect(page.locator('#shared-database-nav').getByRole('link',{name:'Browse records'})).toBeFocused();
  await database.focus(); await page.keyboard.press('ArrowDown');
  await expect(page.locator('#shared-database-nav').getByRole('link',{name:'Browse records'})).toBeFocused();
  await page.keyboard.press('Escape'); await expect(database).toBeFocused();
  await database.click(); await page.locator('#shared-database-nav').getByRole('link',{name:'Downloads',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Downloads',exact:true})).toBeVisible();
  expect(new URL(page.url()).hash).toContain('map=%23%2Fmap%3Ff1a%3Dfield');
  await page.getByRole('button',{name:'About',exact:true}).click();
  await expect(page.locator('#shared-about-nav').getByRole('link')).toHaveText(['Overview','Sources & methodology','FAQ','Help']);
  await page.locator('#shared-about-nav').getByRole('link',{name:'FAQ'}).click();
  await expect(page.getByRole('heading',{name:'FAQ',exact:true})).toBeVisible();
  await expect(page.getByRole('contentinfo',{name:'Project information'})).toBeVisible();
});

test('private Database category filtering reaches the repository and resets paging and selection', async ({ page }) => {
  await isolate(page); const urls: URL[] = [];
  await page.route('**/dev/real-preview/locations?**', async route => { const url = new URL(route.request().url()); urls.push(url); const filtered = url.searchParams.has('category_keys'); const paged = url.searchParams.has('cursor'); await route.fulfill({ contentType:'application/json', body:JSON.stringify({ api_version:'real-preview-v1', data:[candidate(paged ? second : id)], meta:{private_preview:true,next_cursor:filtered || paged ? null : 'synthetic-next-page'} }) }); });
  await page.goto('./#/database?f1a=field');
  await expect(page.getByRole('heading',{name:'Browse records'})).toBeVisible();
  await expect(page.getByRole('columnheader')).toHaveText(['Name','Activity','Place','Source','Location precision']);
  await expect(page.getByRole('complementary',{name:'Selected record'})).toHaveCount(0);
  await page.getByRole('button',{name:'Synthetic first record',exact:true}).click();
  await expect(page.getByRole('complementary',{name:'Selected record'})).toBeVisible();
  await page.getByRole('button',{name:'Load more',exact:true}).click();
  await expect(page.getByText('2 records loaded',{exact:true})).toBeVisible();
  expect(urls.at(-1)!.searchParams.get('cursor')).toBe('synthetic-next-page');
  await page.getByRole('checkbox',{name:'Slaughter',exact:true}).check();
  await expect(page.getByText('1 record loaded',{exact:true})).toBeVisible();
  expect(urls.at(-1)!.searchParams.get('category_keys')).toBe('slaughter');
  expect(urls.at(-1)!.searchParams.has('cursor')).toBe(false);
  await expect(page.getByRole('complementary',{name:'Selected record'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Synthetic first record',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Clear filters',exact:true}).click();
  await expect(page.getByRole('checkbox',{name:'Slaughter',exact:true})).not.toBeChecked();
  expect(urls.at(-1)!.searchParams.has('category_keys')).toBe(false);
  await page.setViewportSize({width:375,height:844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole('button',{name:'Synthetic first record',exact:true})).toBeVisible();
});

test('public Database uses public routes and reports unavailable releases without invented totals', async ({ page }) => {
  await isolate(page,true); const privateReads: string[] = []; page.on('request',request => { if (new URL(request.url()).pathname.startsWith('/dev/')) privateReads.push(request.url()); });
  await page.goto('./#/database'); await expect(page.getByRole('heading',{name:'Browse records'})).toBeVisible();
  await expect(page.getByText('No eligible public release is available yet.',{exact:true})).toBeVisible();
  await expect(page.getByRole('complementary',{name:'Selected record'})).toHaveCount(0);
  expect(privateReads).toEqual([]);
});

test('public record navigation reads the selected release and unavailable records stay empty', async ({ page }) => {
  await isolate(page,true); const reads: URL[] = [];
  const wire = publicWire;
  await page.route('**/api/v2/locations?**',route => route.fulfill({contentType:'application/json',body:JSON.stringify({api_version:'v2',data:[wire],meta:{release_id:'synthetic-release',ruleset_version:'synthetic-rules',profile:'official',next_cursor:null,coverage_note:'Synthetic release only.'}})}));
  await page.route(`**/api/v2/locations/${id}?**`,route => { reads.push(new URL(route.request().url())); return route.fulfill({contentType:'application/json',body:JSON.stringify({api_version:'v2',data:wire,meta:{release_id:'synthetic-release',ruleset_version:'synthetic-rules',profile:'official',release_created_at:'2026-01-01T00:00:00Z'}})}); });
  await page.goto('./#/database'); await page.getByRole('button',{name:'Synthetic public record',exact:true}).click();
  await page.getByRole('link',{name:'Open record page',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Synthetic public record',exact:true})).toBeVisible();
  expect(reads[0]!.searchParams.get('release_id')).toBe('synthetic-release'); expect(reads[0]!.searchParams.get('profile')).toBe('official');
  await expect(page.getByText('Unmapped',{exact:false}).first()).toBeVisible();
  await expect(page.getByRole('button',{name:'Copy record id',exact:true})).toBeVisible();
  await page.route(`**/api/v2/locations/${second}?**`,route => route.fulfill({status:404,contentType:'application/json',body:'{}'}));
  await page.goto(`./#/records/${second}?profile=official&release_id=synthetic-release`);
  await expect(page.getByRole('heading',{name:'Record unavailable',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Synthetic public record',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Copy record id',exact:true})).toHaveCount(0);
});

test('an explicit public record stays public under the combined preview marker', async ({ page }) => {
  await isolate(page);
  await page.route('**/v2-preview/',async route => { const response = await route.fetch(); await route.fulfill({response,body:(await response.text()).replace('<head>','<head><meta name="uec-local-data-mode" content="real-preview">')}); });
  let privateReads = 0; let publicReads = 0;
  page.on('request',request => { if (new URL(request.url()).pathname.startsWith('/dev/')) privateReads += 1; });
  await page.route(`**/api/v2/locations/${id}?**`,route => { publicReads += 1; return route.fulfill({contentType:'application/json',body:JSON.stringify({api_version:'v2',data:publicWire,meta:{release_id:'synthetic-release',ruleset_version:'synthetic-rules',profile:'official',release_created_at:'2026-01-01T00:00:00Z'}})}); });
  await page.goto(`./#/records/${id}?profile=official&release_id=synthetic-release`);
  await expect(page.getByRole('heading',{name:'Synthetic public record',exact:true})).toBeVisible();
  expect(publicReads).toBe(1); expect(privateReads).toBe(0);
  await expect(page.getByText('PRIVATE DEVELOPMENT PREVIEW · NOT PUBLICATION-APPROVED',{exact:true})).toHaveCount(0);
});

test('Downloads scope and community warning are explicit and FAQ remains compact on mobile', async ({ page }) => {
  await isolate(page,true);
  await page.route('**/api/v2/releases/manifest?**', route => route.fulfill({contentType:'application/json',body:JSON.stringify({api_version:'v2',data:{release_id:'synthetic-release',profile:new URL(route.request().url()).searchParams.get('profile'),manifest:{},manifest_sha256:'a'.repeat(64),suppression_generation:1}})}));
  await page.goto('./#/database/downloads');
  await expect(page.getByRole('link',{name:'CSV (up to 1,000 records)'})).toHaveAttribute('href','/api/v2/locations.csv?profile=official');
  await page.getByLabel('Dataset').selectOption('community');
  await expect(page.getByText('Unreviewed community claim — not verified by Until Every Cage.',{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'CSV (up to 1,000 records)'})).toHaveAttribute('href','/api/v2/locations.csv?profile=community');
  await expect(page.getByText(/independent of Browse records filters/)).toBeVisible();
  await page.goto('./#/about/faq'); await page.setViewportSize({width:375,height:844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole('heading',{name:'How do I check its progress?'})).toBeVisible();
});

test('Downloads distinguishes no release from a service failure and keeps its spec available', async ({ page }) => {
  await isolate(page,true); let responseStatus = 404;
  await page.route('**/api/v2/releases/manifest?**',route => route.fulfill({status:responseStatus,contentType:'application/json',body:'{}'}));
  await page.goto('./#/database/downloads');
  await expect(page.getByText('No public release is available yet.',{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:/CSV|Paginated JSON/})).toHaveCount(0);
  await expect(page.getByRole('link',{name:'OpenAPI specification'})).toBeVisible();
  responseStatus = 503; await page.getByLabel('Dataset').selectOption('secondary');
  await expect(page.getByText('Release availability could not be checked. Try again.',{exact:true})).toBeVisible();
  await expect(page.getByText('No public release is available yet.',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Retry',exact:true})).toBeVisible();
});

test('optional email is private and receipt copying, fallback, and status work without persistence', async ({ page }) => {
  test.skip(process.env.VITE_COMMUNITY_PILOT !== 'true','Requires local intake UI.');
  await isolate(page,true);
  await page.addInitScript(() => { Object.defineProperty(navigator,'clipboard',{value:{writeText:async(value:string) => { (window as unknown as {syntheticCopy:string}).syntheticCopy=value; }},configurable:true}); });
  let submitted: Record<string,unknown> | undefined; let statusBody: Record<string,unknown> | undefined;
  await page.route('**/api/community/submissions', async route => { submitted=route.request().postDataJSON(); await route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({submission_id:id,receipt_secret:secret,status:'received',contact_email:email})}); });
  await page.route('**/api/community/status', async route => { statusBody=route.request().postDataJSON(); await route.fulfill({contentType:'application/json',body:JSON.stringify({submission_id:id,status:'screened',contact_email:email})}); });
  await page.goto('./#/contribute?type=evidence');
  await page.getByLabel('Record link or ID',{exact:true}).fill(second); await page.getByLabel('What did you find?').fill('Synthetic evidence');
  await page.getByLabel('Email (optional)',{exact:true}).fill(email); await page.getByLabel(/I have permission/).check();
  await page.getByRole('button',{name:'Send for review'}).click();
  await expect(page.getByRole('heading',{name:'Contribution received'})).toBeVisible();
  expect(submitted!.contact_email).toBe(email);
  await expect(page.getByText(email,{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Copy submission id',exact:true}).click();
  await expect(page.getByText('Submission ID copied.',{exact:true})).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as {syntheticCopy:string}).syntheticCopy)).toBe(id);
  await page.evaluate(() => Object.defineProperty(navigator,'clipboard',{value:{writeText:async() => {throw new Error('synthetic unavailable');}},configurable:true}));
  await page.getByRole('button',{name:'Copy private receipt',exact:true}).click();
  const receipt=page.getByLabel('Private receipt',{exact:true}); await expect(receipt).toBeFocused();
  expect(await receipt.evaluate(element => (element as HTMLInputElement).selectionEnd!-(element as HTMLInputElement).selectionStart!)).toBe(secret.length);
  expect(page.url()).not.toContain(secret); expect(page.url()).not.toContain(email);
  expect(await page.evaluate(() => JSON.stringify({...localStorage,...sessionStorage}))).not.toContain(email);
  expect(await page.evaluate(() => JSON.stringify({...localStorage,...sessionStorage}))).not.toContain(secret);
  await page.getByRole('link',{name:'Check contribution status',exact:true}).click();
  await page.getByLabel('Submission ID',{exact:true}).fill(id); await page.getByLabel('Private receipt',{exact:true}).fill(secret);
  await page.getByRole('button',{name:'Check status',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Privacy screened',exact:true})).toBeVisible();
  await expect(page.getByText(/This does not verify the facts or approve publication/)).toBeVisible();
  expect(statusBody).toEqual({submission_id:id,receipt_secret:secret});
  await page.getByRole('link',{name:'Contribute',exact:true}).click();
  await expect(page.getByLabel('Email (optional)',{exact:true})).toHaveValue('');
  await expect(page.getByLabel('Private receipt',{exact:true})).toHaveCount(0);
});

test('record details copy an ID and link and prefill correction and privacy requests', async ({ page }) => {
  await isolate(page); await page.route(`**/dev/real-preview/locations/${id}`,route => route.fulfill({contentType:'application/json',body:JSON.stringify({api_version:'real-preview-v1',data:candidate()})}));
  await page.goto(`./#/records/${id}?f1a=field`);
  await expect(page.getByRole('button',{name:'Copy record id',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Copy record link',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Suggest a correction',exact:true})).toHaveAttribute('href',new RegExp(`target=${id}`));
  await expect(page.getByRole('link',{name:'Privacy or removal',exact:true})).toHaveAttribute('href',new RegExp(`target=${id}`));
});
