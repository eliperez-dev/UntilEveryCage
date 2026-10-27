import { test, expect, type Page } from '@playwright/test';

const syntheticRelease = 'synthetic-landing-release';
async function installLandingSummary(page: Page) {
  await page.route('**/api/v2/releases/manifest?**', route => route.fulfill({ json: { api_version: 'v2', data: { profile: 'official', release_id: new URL(route.request().url()).searchParams.get('release_id') ?? syntheticRelease, manifest: {}, manifest_sha256: 'a'.repeat(64), suppression_generation: 1 } } }));
  await page.route('**/api/v2/discovery/facets?**', route => {
    const params=new URL(route.request().url()).searchParams,precision=params.get('display_precision');
    const dimensions=precision ? {display_precision:[{value:precision,count:precision==='source_reported'?8000:2005}],country_code:precision==='source_reported'?[{value:'DK',count:5000},{value:'US',count:3000}]:[{value:'US',count:2000},{value:'DK',count:5}]} : {display_precision:[{value:'source_reported',count:8000},{value:'approximate',count:2005},{value:'unmapped',count:2340}],source_id:[{value:'synthetic-a',count:5000},{value:'synthetic-b',count:4000},{value:'synthetic-c',count:3345}]};
    return route.fulfill({json:{api_version:'v2',meta:{profile:'official',release_id:params.get('release_id')??syntheticRelease,ruleset_version:'synthetic-rules',release_created_at:'2026-01-01T00:00:00Z',coverage_scope:'Synthetic public records',count_semantics:'Synthetic records',filters:precision?{display_precision:precision}:{}},dimensions}});
  });
}
test.beforeEach(async ({ page }) => installLandingSummary(page));
const onlySummaryRequests = (requests: readonly string[]) => requests.every(url => ['/api/v2/releases/manifest', '/api/v2/discovery/facets'].includes(new URL(url).pathname));

test('landing stays separate from the map and its media can be paused', async ({ page }) => {
  const apiRequests: string[] = [];
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url()); });
  await page.goto('./');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('HIDDEN INPLAIN SIGHT.');
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link')).toHaveText(['Map', 'Data', 'Contribute', 'About']);
  await expect(page.locator('.masthead nav [aria-current]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Dark theme', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'More tools', exact: true })).toBeVisible();
  await expect(page.locator('.hero-photo')).toHaveCount(2);
  await expect.poll(() => page.locator('.hero-photo').evaluateAll(images => images.every(image => (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0))).toBe(true);
  await expect(page.locator('.maplibregl-map')).toHaveCount(0);
  expect(onlySummaryRequests(apiRequests)).toBe(true);
  await page.getByRole('button', { name: 'Pause background animation' }).click();
  await expect.poll(() => page.locator('.cow').evaluate(image => image.getAnimations().map(animation => animation.playState))).toEqual(['paused', 'paused']);
  await page.getByRole('button', { name: 'Resume background animation' }).click();
  await expect.poll(() => page.locator('.cow').evaluate(image => image.getAnimations().map(animation => animation.playState))).toEqual(['running', 'running']);
  await page.getByRole('link', { name: 'Open the map', exact: true }).first().click();
  await expect.poll(() => new URL(page.url()).hash.split('?')[0]).toBe('#/map');
  await expect(page.locator('.landing-page')).toHaveCount(0);
  await page.goBack();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('HIDDEN INPLAIN SIGHT.');
});

test('landing supports narrow screens, keyboard entry and reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto('./');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.locator('.pig')).toHaveCSS('animation-name', 'none');
  await expect(page.locator('.cow')).toBeHidden();
  await expect(page.locator('.motion-toggle')).toHaveCount(0);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  expect(new URL(page.url()).hash).toBe('');
  for (const link of ['Map', 'Data', 'Contribute', 'About']) await expect(page.getByRole('navigation').getByRole('link', { name: link, exact: true })).toBeVisible();
});

test('saved Spanish choice applies to the landing and shared header in both themes', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('uec-language', 'es'));
  await page.setViewportSize({ width: 320, height: 760 });
  await page.goto('./#/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('OCULTO APLENA VISTA.');
  await expect(page.getByRole('link', { name: 'Abrir el mapa', exact: true }).first()).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Navegación principal' });
  await expect(nav.getByRole('link')).toHaveText(['Mapa', 'Datos', 'Contribuir', 'Acerca de']);
  for (const theme of ['dark', 'light'] as const) {
    if (theme === 'light') await page.locator('.masthead .theme-toggle').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const link of await nav.getByRole('link').all()) {
      await expect(link).toBeVisible();
      const box = await link.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(320);
    }
    await page.getByRole('button', { name: 'Idioma', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Idioma', exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Idioma', exact: true })).toBeFocused();
    await page.getByRole('button', { name: 'Más herramientas', exact: true }).click();
    await expect(page.getByRole('combobox', { name: 'Versión actual', exact: true })).toBeDisabled();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Más herramientas', exact: true })).toBeFocused();
  }
});

test('landing shared navigation preserves map context without loading map data', async ({ page }) => {
  const apiRequests: string[] = [];
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url()); });
  await page.goto('./#/?lat=52&lon=5&z=6&release_id=synthetic-landing-context');
  const mapHref = '#/map?lat=52&lon=5&z=6&release_id=synthetic-landing-context';
  const nav = page.getByRole('navigation', { name: 'Primary' });
  await expect(nav.getByRole('link', { name: 'Map', exact: true })).toHaveAttribute('href', mapHref);
  await expect(nav.getByRole('link', { name: 'Data', exact: true })).toHaveAttribute('href', `#/database/api?map=${encodeURIComponent(mapHref)}`);
  await expect(nav.getByRole('link', { name: 'Contribute', exact: true })).toHaveAttribute('href', `#/contribute?map=${encodeURIComponent(mapHref)}`);
  await expect(page.getByRole('link', { name: 'Open the map', exact: true }).first()).toHaveAttribute('href', mapHref);
  await expect(page.locator('.maplibregl-map')).toHaveCount(0);
  expect(onlySummaryRequests(apiRequests)).toBe(true);
});

test('landing shows release-scoped totals and category shortcuts without loading facilities or requesting device location', async ({ page }) => {
  await page.addInitScript(() => { (window as any).__locationRequests = 0; Object.defineProperty(navigator, 'geolocation', { value: { getCurrentPosition() { (window as any).__locationRequests += 1; } }, configurable: true }); });
  const requests: string[] = []; page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) requests.push(request.url()); });
  await page.goto('./#/?lat=12&lon=3&z=5&release_id=synthetic-selected-release');
  await expect(page.locator('.release-totals dd')).toHaveText(['12,345', '10,005', '3', '2']);
  const links = page.getByRole('navigation', { name: 'Explore by activity' }).getByRole('link');
  await expect(links).toHaveCount(6);
  const href = await links.filter({ hasText: 'Processing' }).getAttribute('href');
  const params = new URLSearchParams(href!.split('?')[1]);
  expect(params.get('release_id')).toBe('synthetic-selected-release'); expect(params.get('category')).toBe('processing_and_preparation'); expect(params.get('list')).toBe('open'); expect(params.get('lat')).toBe('12');
  expect(await page.evaluate(() => (window as any).__locationRequests)).toBe(0);
  expect(onlySummaryRequests(requests)).toBe(true);
  if(process.env.UEC_AREA_CAPTURE_DIR){await page.locator('.discovery').screenshot({path:`${process.env.UEC_AREA_CAPTURE_DIR}/landing-totals-desktop.png`});await page.setViewportSize({width:320,height:760});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.locator('.release-totals').screenshot({path:`${process.env.UEC_AREA_CAPTURE_DIR}/landing-totals-mobile.png`});}
});

test('nearby landing action requests location explicitly, blocks duplicate taps and reports denial', async ({ page }) => {
  await page.addInitScript(() => { (window as any).__locationRequests = 0; Object.defineProperty(navigator, 'geolocation', { value: { getCurrentPosition(_success: unknown, failure: (error: {code:number}) => void) { (window as any).__locationRequests += 1; (window as any).__denyLocation = () => failure({ code: 1 }); } }, configurable: true }); });
  await page.goto('./');
  const nearby = page.getByRole('button', { name: 'Find locations near me', exact: true });
  await expect(nearby).toBeVisible(); expect(await page.evaluate(() => (window as any).__locationRequests)).toBe(0);
  await nearby.click();
  await expect(page.getByRole('button', { name: 'Finding your location…', exact: true })).toBeDisabled();
  expect(await page.evaluate(() => (window as any).__locationRequests)).toBe(1);
  await page.evaluate(() => (window as any).__denyLocation());
  await expect(page.getByRole('alert')).toHaveText('Location permission was denied.');
  await expect(nearby).toBeEnabled(); expect(new URL(page.url()).hash).toBe('');
});

test('a late landing location reply cannot navigate after leaving the page', async ({ page }) => {
  await page.addInitScript(() => { Object.defineProperty(navigator, 'geolocation', { value: { getCurrentPosition(success: (position: unknown) => void) { (window as any).__finishLocation = () => success({ coords: { latitude: 12.345678, longitude: 65.432109 } }); } }, configurable: true }); });
  await page.goto('./'); await page.getByRole('button', { name: 'Find locations near me', exact: true }).click();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'About', exact: true }).click();
  await expect(page.locator('.landing-page')).toHaveCount(0);
  await page.evaluate(() => (window as any).__finishLocation());
  expect(new URL(page.url()).hash.split('?')[0]).toBe('#/about'); expect(page.url()).not.toContain('12.345678');
});

test('landing aggregate failure offers retry without removing map entry', async ({ page }) => {
  let failed = true;
  await page.route('**/api/v2/discovery/facets?**', async route => { if (failed) await route.fulfill({ status: 503, json: {} }); else await route.fallback(); });
  await page.goto('./'); await expect(page.getByText('Release totals are unavailable.', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open the map', exact: true }).first()).toBeVisible();
  failed = false; await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.locator('.release-totals dd')).toHaveText(['12,345', '10,005', '3', '2']);
});

test('capped or unavailable mapped-country facets preserve other totals and never show a false country count',async({page})=>{
  let fail=true;
  await page.route('**/api/v2/discovery/facets?**',async route=>{
    const params=new URL(route.request().url()).searchParams,precision=params.get('display_precision');if(!precision)return route.fallback();
    if(fail)return route.fulfill({status:503,json:{}});
    return route.fulfill({json:{api_version:'v2',meta:{profile:'official',release_id:params.get('release_id'),ruleset_version:'synthetic-rules',release_created_at:'2026-01-01T00:00:00Z',coverage_scope:'Synthetic',count_semantics:'Synthetic records',filters:{display_precision:precision}},dimensions:{display_precision:[{value:precision,count:precision==='source_reported'?8000:2005}],country_code:[{value:'DK',count:1}]}}});
  });
  await page.goto('./');await expect(page.locator('.release-totals dd')).toHaveText(['12,345','10,005','3','Unavailable']);
  fail=false;await page.reload();await expect(page.locator('.release-totals dd')).toHaveText(['12,345','10,005','3','Unavailable']);
  await expect(page.getByRole('link',{name:'Open the map',exact:true}).first()).toBeVisible();
});
