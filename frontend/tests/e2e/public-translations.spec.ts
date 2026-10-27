import { expect, test, type Page } from '@playwright/test';
import { installEmptyPublicMap } from '../fixtures/empty-public-map';
import { es } from '../../src/app/locales/es';
import { readFileSync } from 'node:fs';
const [fr,de,nl,da]=['fr','de','nl','da'].map(code=>JSON.parse(readFileSync(new URL('../../src/app/locales/'+code+'.json',import.meta.url),'utf8')) as Record<string,string>);
const locales = [{code:'en',name:'English',messages:null},{code:'es',name:'Español',messages:es},{code:'fr',name:'Français',messages:fr},{code:'de',name:'Deutsch',messages:de},{code:'nl',name:'Nederlands',messages:nl},{code:'da',name:'Dansk',messages:da}];
const text = (locale:typeof locales[number],key:string) => locale.messages ? (locale.messages as Record<string,string>)[key] ?? key : key;
async function select(page:Page, name:string){await page.locator('.language-action').click();await page.locator('#shared-language-menu').getByRole('button',{name,exact:true}).click();await expect(page.locator('#shared-language-menu')).toHaveCount(0);}
async function setup(page:Page){
  await page.route('https://**/*',route=>route.abort());
  await installEmptyPublicMap(page,'synthetic-public-translation');
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(!path.startsWith('/api/'))return route.fallback();
    if(!['GET','HEAD'].includes(route.request().method()))return route.abort();
    if(path==='/api/community/capabilities')return route.fulfill({json:{enabled:true,types:['facility','evidence','correction','duplicate','privacy_removal']}});
    if(path.startsWith('/api/v2/'))return route.fallback();
    return route.fulfill({status:404,json:{}});
  });
  await page.addInitScript(()=>{(window as unknown as {SwaggerUIBundle:unknown}).SwaggerUIBundle=Object.assign((options:{onComplete?:()=>void})=>{queueMicrotask(()=>options.onComplete?.());return{unmount(){}};},{presets:{apis:{}}});});
}

test('all six languages translate About paragraphs, FAQ and outreach copy',async({page})=>{
  test.setTimeout(90_000);await setup(page);await page.goto('./#/about');
  const project="is an instrument of exposure. We aggregate public government data to map the global infrastructure of animal exploitation. From slaughterhouses and vivisection labs to commercial breeders, we bring the industry's hidden network into a single, searchable interface.";
  const faq='Government datasets are collected, cleaned and standardized, with links back to their sources. Address lookups add coordinates, and matching connects related records. Dated releases supply the map, search and downloads through a Rust API.';
  for(const locale of locales){
    await page.goto('./#/about');await select(page,locale.name);await expect(page.locator('html')).toHaveAttribute('lang',locale.code);
    await expect(page.locator('.manifesto>p').first()).toContainText(text(locale,project));
    await expect(page.locator('.manifesto>ul').first().locator('li').first()).toContainText(text(locale,'Piglets are castrated and tails are docked without anesthesia. Cows are dehorned with burning irons. Chickens are debeaked with hot blades.'));
    await expect(page.locator('.manifesto')).toContainText(text(locale,'By mapping this concealed infrastructure, we aim to:'));
    await expect(page.locator('#technology>p')).toHaveText(text(locale,faq));
    await expect(page.locator('#contributions>p').first()).toHaveText(text(locale,'You can suggest a facility, add evidence, suggest a correction, report a possible duplicate, or request a privacy review. Submissions are reviewed separately from the project dataset and do not automatically change a release.'));
    await page.goto('./#/');await expect(page.locator('.hero-copy>p')).toHaveText(text(locale,'Behind closed doors, animals are bred, confined, experimented on and killed. Until Every Cage maps the industries responsible.'));
    await expect(page.locator('.discovery-heading>p')).toHaveText(text(locale,'Explore farms, slaughterhouses, laboratories and the businesses around them.'));
  }
});

test('public Data explanations and unavailable-record actions translate without changing API values',async({page})=>{
  test.setTimeout(90_000);await setup(page);await page.goto('./#/database/api');
  const explanation='A release is a dated, versioned snapshot. The date identifies its creation; current privacy restrictions still apply to older views. The API ID above selects that specific release.';
  for(const locale of locales){
    await page.goto('./#/database/api');await select(page,locale.name);
    await expect(page.locator('.pagination-note')).toHaveText(text(locale,explanation));
    await expect(page.locator('.release-access select').first()).toHaveValue('official');
    await expect(page.locator('.download-links a').first()).toHaveAttribute('href',/profile=official/);
    await page.goto('./#/records/550e8400-e29b-41d4-a716-446655440000?release_id=synthetic-public-translation');
    await expect(page.locator('.public-record h1')).toHaveText(text(locale,'Record unavailable'));
    await expect(page.locator('.public-record [role=alert]')).toHaveText(text(locale,'This record is unavailable in the selected public release.'));
    await expect(page.locator('.public-record').getByRole('link')).toHaveText(text(locale,'Browse records'));
  }
});

test('public contribution countries, validation and location fallback translate with zero submissions',async({page})=>{
  test.setTimeout(90_000);await setup(page);let writes=0;page.on('request',request=>{if(request.method()==='POST')writes++;});
  await page.addInitScript(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type:string,...args:unknown[]){if(['webgl','webgl2','experimental-webgl'].includes(type))return null;return original.call(this,type,...(args as []));} as typeof HTMLCanvasElement.prototype.getContext;});
  await page.goto('./#/contribute');
  for(const locale of locales){
    await select(page,locale.name);await page.locator('input[name=label]').fill('Synthetic unchanged facility');
    const country=page.locator('select[name=country_code]');await country.selectOption('DE');await expect(country.locator('option:checked')).toHaveText(new Intl.DisplayNames([locale.code],{type:'region'}).of('DE')!);await expect(country).toHaveValue('DE');
    const contact=page.locator('.intake details').filter({has:page.locator('input[name=contact_email]')});if(await contact.getAttribute('open')===null)await contact.locator('summary').click();
    await page.locator('input[name=contact_email]').fill('invalid-email');await page.locator('.consent input').check();await page.locator('.intake button[type=submit]').click();
    await expect(page.locator('.field-error').filter({hasText:text(locale,'Enter a valid email address or leave it blank.')})).toBeVisible();
    await expect(page.locator('input[name=label]')).toHaveValue('Synthetic unchanged facility');
    const location=page.locator('.intake details').filter({has:page.locator('input[name=location_text]')});if(await location.getAttribute('open')===null)await location.locator('summary').click();
    await expect(page.locator('.coordinate-inputs label').first()).toContainText(text(locale,'Latitude'));
    await expect(page.locator('.clear-point')).toHaveText(text(locale,'Clear selected point'));
    await expect(page.locator('.picker-shell [role=status]')).toHaveText(text(locale,'The map could not be opened. You can enter coordinates below instead.'));
  }
  expect(writes).toBe(0);
});
