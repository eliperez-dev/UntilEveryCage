import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{
 await page.route('**/v2-preview/',async route=>{const response=await route.fetch();await route.fulfill({response,body:(await response.text()).replace(/<meta name="uec-local-data-mode" content="real-preview">/g,'')});});
 await page.route('**/api/**',route=>new URL(route.request().url()).pathname.startsWith('/api/')?route.fulfill({status:503,contentType:'application/json',body:'{}'}):route.fallback());
 await page.route('**/dev/real-preview/**',route=>route.abort());
 await page.route('https://tile.openstreetmap.org/**',route=>route.abort());
 await page.route('https://server.arcgisonline.com/**',route=>route.abort());
});

test('public routes use only public release reads and never expose private or fixture rows',async({page})=>{
 const privateRequests:string[]=[];
 page.on('request',request=>{if(/^\/(?:dev|api\/private|api\/community)\//.test(new URL(request.url()).pathname))privateRequests.push(request.url());});
 for(const route of ['#/map','#/database','#/records/synthetic-record-1','#/locations/synthetic-record-1']){
  await page.goto(`./${route}`);await expect(page.getByRole('banner')).toBeVisible();await expect(page.getByRole('main')).toBeVisible();
  await expect(page.getByText(/fixture record|private candidate|synthetic source/i)).toHaveCount(0);
  await expect(page.locator('[data-facility-id]')).toHaveCount(0);
 }
 expect(privateRequests).toEqual([]);
});

test('public map route context does not silently search or enable a community profile',async({page})=>{
 const requests:string[]=[];
 page.on('request',request=>{const url=new URL(request.url());if(url.pathname.startsWith('/api/')||url.pathname.startsWith('/dev/'))requests.push(url.pathname+url.search);});
 await page.goto('./?mode=local-v2#/map?profile=community&query=private%20address');
 await expect(page.getByRole('heading',{name:'Map'})).toBeVisible();
 expect(requests.every(url=>url.startsWith('/api/v2/releases/manifest?profile=official'))).toBe(true);
});

test('an unavailable new record cannot retain the previous public record identity',async({page})=>{
 let reads=0;
 await page.route('**/api/v2/locations/*?**',route=>{reads+=1;return route.fulfill({status:404,contentType:'application/json',body:'{}'});});
 await page.goto('./#/records/first-synthetic-record');await expect(page.getByRole('heading',{name:'Record unavailable'})).toBeVisible();
 await page.goto('./#/records/second-synthetic-record');await expect(page.getByRole('heading',{name:'Record unavailable'})).toBeVisible();
 expect(reads).toBe(2);await expect(page.getByText(/first-synthetic-record|second-synthetic-record/)).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Copy record id'})).toHaveCount(0);
});
