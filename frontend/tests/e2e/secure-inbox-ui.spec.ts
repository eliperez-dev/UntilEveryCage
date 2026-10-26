import { expect, test, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { SECURE_CIPHER_BYTES, SECURE_PROTOCOL, type SecureInbox, type SecureStatus, type SecureSubmissionRequest, type PreparedSecureReply } from '../../src/api/SecureCommunityRepository';
import { prepareSecureSubmission, prepareSecureReply, reviewerSession, unlockSecureReviewerKey, verifySecureInbox } from '../../src/features/contributions/secureInbox';

test.use({ trace: 'off', video: 'off', screenshot: 'off' });
test.skip(process.env.UEC_SECURE_UI_TEST !== 'true', 'Requires the explicit local encrypted inbox preview and synthetic key fixture.');
const fixturePath=resolve(process.env.UEC_SECURE_UI_KEY_BUNDLE??'../target/secure-inbox-integration/local-reviewer-recovery.json');
type Fixture={publicKey:string;fingerprint:string;encryptedExport:string;recoverySecret:string};
const date='2026-10-26T12:00:00Z';
const syntheticName='Synthetic encrypted UI facility';
function capabilities(key:Fixture){return {enabled:true,mode:'embedded_sdk',provider:'openpgpjs-self-hosted',security_status:'experimental_local_only',protocol:SECURE_PROTOCOL,reviewer_public_key:key.publicKey,reviewer_fingerprint:key.fingerprint,replies:true,email_alerts:false,max_ciphertext_bytes:SECURE_CIPHER_BYTES} as const;}
function serverInbox(request:SecureSubmissionRequest):SecureInbox{return {case_id:request.case_id,kind:request.kind,status:'received',contributor_fingerprint:request.contributor_fingerprint,reviewer_fingerprint:request.reviewer_fingerprint,contributor_public_key:request.contributor_public_key,reviewer_public_key:'',created_at:date,updated_at:date,expires_at:'2026-11-26T12:00:00Z',messages:[{message_id:request.initial_message_id,ordinal:1,author:'contributor',ciphertext:request.ciphertext,created_at:date}]};}
type Relay={inbox:SecureInbox|null;request:SecureSubmissionRequest|null;capability:'ready'|'disabled'|'mismatch';submitFailures:number;replyFailures:number;reviewFailures:number;submitBodies:string[];replyBodies:string[];reviewBodies:string[];plaintextWrites:number;secureWrites:number;denyContributor:boolean;denyReviewer:boolean;dropAcknowledgedReply:boolean};
function relay():Relay{return {inbox:null,request:null,capability:'ready',submitFailures:0,replyFailures:0,reviewFailures:0,submitBodies:[],replyBodies:[],reviewBodies:[],plaintextWrites:0,secureWrites:0,denyContributor:false,denyReviewer:false,dropAcknowledgedReply:false};}
async function mock(page:Page,key:Fixture,state:Relay){
  await page.route('**/*',route=>{const url=new URL(route.request().url());return url.protocol.startsWith('http')&&!['127.0.0.1','localhost'].includes(url.hostname)?route.abort():route.fallback();});
  // No legacy submission or unhandled write can leave this synthetic test.
  await page.route('**/api/**',route=>route.request().method()==='GET'?route.fallback():route.fulfill({status:403,contentType:'application/json',body:'{}'}));
  await page.route('**/api/community/submissions',route=>{state.plaintextWrites++;return route.fulfill({status:403,body:'{}'});});
  await page.route('**/api/**/secure/**',async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    const json=(body:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(path.endsWith('/capabilities'))return json(state.capability==='disabled'?{enabled:false}:{...capabilities(key),...(state.capability==='mismatch'?{reviewer_fingerprint:'a'.repeat(40)}:{})});
    if(request.method()!=='GET')state.secureWrites++;
    if(path==='/api/community/secure/submissions'){
      const body=request.postData()??'';state.submitBodies.push(body);
      const payload=request.postDataJSON() as SecureSubmissionRequest;
      if(!state.request){state.request=payload;state.inbox={...serverInbox(payload),reviewer_public_key:key.publicKey};}
      if(state.submitFailures-->0)return json({},503);
      return json({case_id:payload.case_id,status:state.inbox!.status,created_at:date,expires_at:state.inbox!.expires_at},201);
    }
    if(path==='/api/community/secure/inbox'){
      const auth=request.postDataJSON() as {case_id:string;access_secret:string};
      if(!state.inbox||state.inbox.status==='removed'||auth.case_id!==state.inbox.case_id||auth.access_secret!==state.request?.access_secret)return json({},404);
      return json(state.inbox);
    }
    if(path==='/api/community/secure/messages'||path==='/api/private/community/secure/messages'){
      const reviewer=path.includes('/private/'),body=request.postData()??'';
      (reviewer?state.reviewBodies:state.replyBodies).push(body);
      if(reviewer?state.denyReviewer:state.denyContributor)return json({},403);
      if(reviewer?state.reviewFailures-->0:state.replyFailures-->0)return json({},503);
      const payload=request.postDataJSON() as PreparedSecureReply&{case_id:string};
      if(!state.inbox||state.inbox.status==='closed'||state.inbox.status==='removed')return json({},404);
      if(!state.dropAcknowledgedReply&&!state.inbox.messages.some(message=>message.message_id===payload.message_id))state.inbox={...state.inbox,messages:[...state.inbox.messages,{message_id:payload.message_id,ordinal:state.inbox.messages.length+1,author:reviewer?'reviewer':'contributor',ciphertext:payload.ciphertext,created_at:date}]};
      return json({case_id:payload.case_id,message_id:payload.message_id,status:'stored'},201);
    }
    if(path==='/api/private/community/secure/queue')return json({cases:state.inbox?[state.inbox]:[]});
    if(path==='/api/private/community/secure/inbox')return state.inbox&&state.inbox.status!=='removed'?json(state.inbox):json({},404);
    if(path==='/api/private/community/secure/disposition'){
      const payload=request.postDataJSON() as {case_id:string;status:SecureStatus};if(!state.inbox)return json({},404);
      state.inbox={...state.inbox,status:payload.status};return json({case_id:payload.case_id,status:payload.status});
    }
    return json({},404);
  });
}
async function fillFacility(page:Page){await page.getByLabel('Facility name').fill(syntheticName);await page.getByLabel(/I have permission/).check();}
async function recovered(page:Page,armor:string,key:string){await page.getByLabel('Recovery file',{exact:true}).setInputFiles({name:'synthetic-recovery.asc',mimeType:'text/plain',buffer:Buffer.from(armor)});await expect(page.getByText('Recovery file ready.',{exact:true})).toBeVisible();await page.getByLabel('Recovery key',{exact:true}).fill(key);await page.getByRole('button',{name:'Open inbox',exact:true}).click();}

test('disabled or mismatched capability never falls back to plaintext intake',async({page})=>{
  const key=JSON.parse(await readFile(fixturePath,'utf8')) as Fixture,state=relay();await mock(page,key,state);
  for(const value of ['disabled','mismatch'] as const){state.capability=value;await page.goto('#/contribute');await expect(page.getByRole('heading',{name:'Encrypted intake unavailable',exact:true})).toBeVisible();await expect(page.getByLabel('Facility name')).toHaveCount(0);expect(state.plaintextWrites===0&&state.secureWrites===0).toBe(true);}
  state.capability='ready';await page.getByRole('button',{name:'Retry',exact:true}).click();await expect(page.getByLabel('Facility name')).toBeVisible();
});

test('real encrypted submit, exact retries, inbox refresh and cross-context recovery work without plaintext writes',async({page,browser,baseURL})=>{
  test.setTimeout(90_000);
  const key=JSON.parse(await readFile(fixturePath,'utf8')) as Fixture,state=relay();state.submitFailures=1;state.replyFailures=1;await mock(page,key,state);
  const requestUrls:string[]=[];page.on('request',r=>requestUrls.push(r.url()));
  await page.goto('#/contribute');await fillFacility(page);await page.getByRole('button',{name:'Send for review',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Submission not confirmed',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Download recovery file',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Retry encrypted submission',exact:true}).click();await expect(page.getByRole('heading',{name:'Submission received',exact:true})).toBeVisible();
  expect(state.submitBodies.length===2&&state.submitBodies[0]===state.submitBodies[1]).toBe(true);
  expect(state.submitBodies.every(body=>!body.includes(syntheticName)&&!body.includes('PRIVATE KEY'))).toBe(true);
  const recoveryKey=await page.getByLabel('Recovery key',{exact:true}).inputValue();
  const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Download recovery file',exact:true}).click();const download=await downloadEvent;expect(download.suggestedFilename()).toMatch(/^uec-inbox-[a-f0-9-]+\.asc$/);
  const downloadedPath=await download.path();expect(Boolean(downloadedPath)).toBe(true);const armor=await readFile(downloadedPath!,'utf8');
  await page.getByRole('link',{name:'Open private inbox',exact:true}).click();await expect(page.locator('.messages').getByText(syntheticName,{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Refresh inbox',exact:true}).click();await expect(page.locator('.messages>li')).toHaveCount(1);
  await page.getByLabel('Reply to reviewer',{exact:true}).fill('Synthetic contributor reply');await page.getByRole('button',{name:'Send encrypted reply',exact:true}).click();
  await expect(page.getByRole('button',{name:'Retry encrypted reply',exact:true})).toBeVisible();await page.getByRole('button',{name:'Retry encrypted reply',exact:true}).click();await expect(page.locator('.messages>li')).toHaveCount(2);
  expect(state.replyBodies.length===2&&state.replyBodies[0]===state.replyBodies[1]).toBe(true);expect(state.replyBodies.every(body=>!body.includes('Synthetic contributor reply'))).toBe(true);
  const reviewer=await unlockSecureReviewerKey(key.encryptedExport,key.recoverySecret,key.fingerprint),reviewSession=await reviewerSession(state.inbox!,reviewer,key.fingerprint);await verifySecureInbox(state.inbox!,reviewSession);const reply=await prepareSecureReply(reviewSession,'Synthetic reviewer reply');
  state.inbox={...state.inbox!,status:'needs_information',messages:[...state.inbox!.messages,{message_id:reply.message_id,ordinal:3,author:'reviewer',ciphertext:reply.ciphertext,created_at:date}]};
  await page.getByRole('button',{name:'Refresh inbox',exact:true}).click();await expect(page.locator('.messages').getByText('Synthetic reviewer reply',{exact:true})).toBeVisible();await expect(page.locator('.messages>li')).toHaveCount(3);
  let failedRefresh=true;
  await page.route('**/api/community/secure/inbox',route=>{if(failedRefresh){failedRefresh=false;return route.fulfill({status:503,contentType:'application/json',body:'{}'});}return route.fallback();});
  await page.getByRole('button',{name:'Refresh inbox',exact:true}).click();await expect(page.locator('.messages')).toHaveCount(0);await expect(page.getByRole('button',{name:'Retry opening inbox',exact:true})).toBeVisible();await page.getByRole('button',{name:'Retry opening inbox',exact:true}).click();await expect(page.locator('.messages>li')).toHaveCount(3);
  await page.getByRole('navigation',{name:'Primary'}).getByRole('link',{name:'Contribute',exact:true}).click();await expect(page.getByLabel('Facility name')).toBeVisible();await page.goBack();await expect(page.locator('.messages>li')).toHaveCount(3);
  expect(state.plaintextWrites).toBe(0);expect(requestUrls.every(url=>!url.includes(state.request!.access_secret))).toBe(true);
  const context=await browser.newContext(),fresh=await context.newPage();await mock(fresh,key,state);await fresh.goto(baseURL+'#/secure-inbox');await recovered(fresh,armor,recoveryKey);await expect(fresh.locator('.messages>li')).toHaveCount(3);
  await fresh.getByRole('button',{name:'Lock inbox',exact:true}).click();await expect(fresh.locator('.messages')).toHaveCount(0);expect(new URL(fresh.url()).hash.includes('access_secret')).toBe(false);
  await recovered(fresh,armor,'a'.repeat(64));await expect(fresh.getByRole('alert')).toBeVisible();await expect(fresh.locator('.messages')).toHaveCount(0);
  await recovered(fresh,armor,recoveryKey);await expect(fresh.locator('.messages>li')).toHaveCount(3);
  state.inbox={...state.inbox!,messages:[...state.inbox!.messages.slice(0,2),{...state.inbox!.messages[2]!,ciphertext:state.inbox!.messages[2]!.ciphertext.replace(/\n([A-Za-z0-9])/,(match,char)=>'\n'+(char==='A'?'B':'A'))}]};
  await fresh.getByRole('button',{name:'Refresh inbox',exact:true}).click();await expect(fresh.getByRole('alert')).toBeVisible();await expect(fresh.locator('.messages')).toHaveCount(0);await context.close();
});

test('reviewer unlock, exact reply retry, persistent history checks and real status controls work',async({page})=>{
  test.setTimeout(90_000);
  const key=JSON.parse(await readFile(fixturePath,'utf8')) as Fixture,state=relay();state.reviewFailures=1;
  const prepared=await prepareSecureSubmission({kind:'facility',label:syntheticName,consent:true},capabilities(key),key.fingerprint);state.request=prepared.request;state.inbox={...serverInbox(prepared.request),reviewer_public_key:key.publicKey};await mock(page,key,state);
  await page.goto('#/secure-review');await page.getByLabel('Reviewer access token',{exact:true}).fill('synthetic-reviewer-token');await page.getByRole('button',{name:'Open review queue',exact:true}).click();await page.locator('.queue-case').click();await expect(page.getByText('Unlock your reviewer key to read this inbox.',{exact:true})).toBeVisible();await expect(page.locator('.messages')).toHaveCount(0);
  await page.getByLabel('Encrypted reviewer key file',{exact:true}).setInputFiles({name:'synthetic-reviewer.asc',mimeType:'text/plain',buffer:Buffer.from(key.encryptedExport)});await expect(page.getByText('Reviewer key file ready.',{exact:true})).toBeVisible();await page.getByLabel('Recovery key',{exact:true}).fill('a'.repeat(64));await page.getByRole('button',{name:'Unlock key locally',exact:true}).click();await expect(page.getByRole('alert')).toBeVisible();await expect(page.locator('.messages')).toHaveCount(0);
  await page.getByLabel('Recovery key',{exact:true}).fill(key.recoverySecret);await page.getByRole('button',{name:'Unlock key locally',exact:true}).click();await expect(page.locator('.messages').getByText(syntheticName,{exact:true})).toBeVisible();
  await page.getByLabel('Reply to contributor',{exact:true}).fill('Synthetic reviewer question');await page.getByRole('button',{name:'Send encrypted reply',exact:true}).click();await expect(page.getByRole('button',{name:'Retry encrypted reply',exact:true})).toBeVisible();await page.getByRole('button',{name:'Retry encrypted reply',exact:true}).click();await expect(page.locator('.messages>li')).toHaveCount(2);
  expect(state.reviewBodies.length===2&&state.reviewBodies[0]===state.reviewBodies[1]).toBe(true);const verified=await verifySecureInbox(state.inbox!,prepared.session);expect(verified[1]?.text==='Synthetic reviewer question').toBe(true);
  await page.getByRole('button',{name:'More information needed',exact:true}).click();await expect(page.locator('.processing-status')).toContainText('More information needed');
  await page.getByRole('button',{name:'Closed',exact:true}).click();await expect(page.getByText('This inbox is closed to new replies.',{exact:true})).toBeVisible();await expect(page.getByLabel('Reply to contributor',{exact:true})).toHaveCount(0);
  const full=state.inbox!;state.inbox={...full,messages:full.messages.slice(0,1)};await page.getByRole('button',{name:'Refresh inbox',exact:true}).click();await expect(page.getByText('The messages could not be verified. No submission text is shown.',{exact:true})).toBeVisible();await expect(page.locator('.messages')).toHaveCount(0);
  state.inbox=full;await page.locator('.queue-case').click();await expect(page.locator('.messages>li')).toHaveCount(2);await page.getByRole('button',{name:'Remove this inbox',exact:true}).click();await expect(page.getByText('Remove the intake and revoke contributor access? This does not change the public map record.',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Confirm inbox removal',exact:true}).click();await expect(page.locator('.messages')).toHaveCount(0);expect(state.inbox?.status==='removed').toBe(true);
  await page.getByRole('button',{name:'Lock review',exact:true}).click();await expect(page.getByLabel('Reviewer access token',{exact:true})).toHaveValue('');await expect(page.locator('.messages')).toHaveCount(0);expect(state.plaintextWrites).toBe(0);
});

test('key setup works with disabled intake and all local screens fit desktop/mobile themes',async({page})=>{
  test.setTimeout(90_000);const key=JSON.parse(await readFile(fixturePath,'utf8')) as Fixture,state=relay();state.capability='disabled';await mock(page,key,state);
  await page.goto('#/secure-review');await page.getByText('Set up a local reviewer key',{exact:true}).click();await page.getByRole('button',{name:'Generate reviewer key locally',exact:true}).click();await expect(page.getByLabel('Public reviewer fingerprint',{exact:true})).toBeVisible();const fingerprint=await page.getByLabel('Public reviewer fingerprint',{exact:true}).inputValue();expect(/^(?:[a-f0-9]{40}|[a-f0-9]{64})$/.test(fingerprint)).toBe(true);expect((await page.getByLabel('Public reviewer key',{exact:true}).inputValue()).startsWith('-----BEGIN PGP PUBLIC KEY BLOCK-----')).toBe(true);expect((await page.locator('body').innerText()).includes('BEGIN PGP PRIVATE KEY BLOCK')).toBe(false);expect(state.secureWrites).toBe(0);
  const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Download encrypted reviewer key',exact:true}).click();expect((await downloadEvent).suggestedFilename()).toBe('uec-reviewer-key.asc');
  state.capability='ready';
  for(const width of [1024,390,320])for(const theme of ['dark','light'])for(const route of ['#/contribute','#/secure-inbox','#/secure-review']){await page.setViewportSize({width,height:844});await page.goto(route);await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
  expect(state.plaintextWrites).toBe(0);
});

test('reply access failures clear contributor plaintext and lock reviewer credentials',async({page})=>{
  test.setTimeout(90_000);const key=JSON.parse(await readFile(fixturePath,'utf8')) as Fixture,state=relay();
  const prepared=await prepareSecureSubmission({kind:'facility',label:syntheticName,consent:true},capabilities(key),key.fingerprint);state.request=prepared.request;state.inbox={...serverInbox(prepared.request),reviewer_public_key:key.publicKey};await mock(page,key,state);
  await page.goto('#/secure-inbox');await recovered(page,prepared.recovery.encryptedExport,prepared.recovery.recoverySecret);await expect(page.locator('.messages>li')).toHaveCount(1);
  state.denyContributor=true;await page.getByLabel('Reply to reviewer',{exact:true}).fill('Synthetic access-denied reply');await page.getByRole('button',{name:'Send encrypted reply',exact:true}).click();await expect(page.locator('.messages')).toHaveCount(0);await expect(page.getByLabel('Recovery file',{exact:true})).toBeVisible();await expect(page.getByRole('alert')).toBeVisible();
  await page.goto('#/secure-review');await page.getByLabel('Reviewer access token',{exact:true}).fill('synthetic-reviewer-token');await page.getByRole('button',{name:'Open review queue',exact:true}).click();await page.locator('.queue-case').click();
  await page.getByLabel('Encrypted reviewer key file',{exact:true}).setInputFiles({name:'synthetic-reviewer.asc',mimeType:'text/plain',buffer:Buffer.from(key.encryptedExport)});await expect(page.getByText('Reviewer key file ready.',{exact:true})).toBeVisible();await page.getByLabel('Recovery key',{exact:true}).fill(key.recoverySecret);await page.getByRole('button',{name:'Unlock key locally',exact:true}).click();await expect(page.locator('.messages>li')).toHaveCount(1);
  state.denyReviewer=true;await page.getByLabel('Reply to contributor',{exact:true}).fill('Synthetic reviewer access-denied reply');await page.getByRole('button',{name:'Send encrypted reply',exact:true}).click();await expect(page.locator('.messages')).toHaveCount(0);await expect(page.getByLabel('Reviewer access token',{exact:true})).toHaveValue('');await expect(page.getByLabel('Recovery key',{exact:true})).toHaveValue('');await expect(page.getByRole('alert')).toBeVisible();expect(state.plaintextWrites).toBe(0);
});

test('an acknowledged reply omitted by the relay fails closed before old plaintext is shown',async({page})=>{
  test.setTimeout(90_000);const key=JSON.parse(await readFile(fixturePath,'utf8')) as Fixture,state=relay();state.dropAcknowledgedReply=true;
  const prepared=await prepareSecureSubmission({kind:'facility',label:syntheticName,consent:true},capabilities(key),key.fingerprint);state.request=prepared.request;state.inbox={...serverInbox(prepared.request),reviewer_public_key:key.publicKey};await mock(page,key,state);
  await page.goto('#/secure-inbox');await recovered(page,prepared.recovery.encryptedExport,prepared.recovery.recoverySecret);await expect(page.locator('.messages>li')).toHaveCount(1);
  await page.getByLabel('Reply to reviewer',{exact:true}).fill('Synthetic acknowledged reply');await page.getByRole('button',{name:'Send encrypted reply',exact:true}).click();await expect(page.locator('.messages')).toHaveCount(0);await expect(page.getByText('The inbox could not be verified. Reopen it with your recovery file.',{exact:true})).toBeVisible();expect(state.inbox!.messages.length===1&&state.replyBodies.length===1).toBe(true);expect(state.plaintextWrites).toBe(0);
});
