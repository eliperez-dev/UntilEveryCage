import { expect, test } from '@playwright/test';
import { installEmptyPublicMap } from '../fixtures/empty-public-map';

test('retired Database bookmarks open map search with safe filters and release context', async ({ page }) => {
  await installEmptyPublicMap(page, 'synthetic-release');
  await page.goto('./#/database?lat=38&lon=-96&z=4&pitch=27&bearing=14&basemap=satellite&release_id=synthetic-release&country=US&category=slaughter&precision=unmapped&q=private%20search&extra=unsafe');
  await expect.poll(() => new URL(page.url()).hash.split('?')[0]).toBe('#/map');
  const params = new URLSearchParams(new URL(page.url()).hash.split('?')[1]);
  for (const [key, value] of Object.entries({ lat:'38', lon:'-96', z:'4', pitch:'27', bearing:'14', basemap:'satellite', release_id:'synthetic-release', country:'US', category:'slaughter', precision:'unmapped', list:'open' })) expect(params.get(key)).toBe(value);
  expect(params.has('q')).toBe(false);
  expect(params.has('extra')).toBe(false);
  await expect(page.getByRole('complementary', { name: 'Search, filters, and results' })).toBeVisible();
  await expect(page.locator('.public-database')).toHaveCount(0);
});

test('FAQ bookmarks become About sections and retain useful links and map context', async ({ page }) => {
  const map = '#/map?lat=44.5&lon=8.1&z=5&country=ES&release_id=synthetic-release';
  await page.goto('./#/faq?section=contributions&map=' + encodeURIComponent(map));
  await expect.poll(() => new URL(page.url()).hash).toBe('#/about?section=contributions&map=' + encodeURIComponent(map));
  await expect(page.getByRole('heading', { level:1, name:'About Until Every Cage is Empty' })).toBeVisible();
  await expect(page.getByRole('heading', { name:'Frequently asked questions', exact:true })).toBeVisible();
  await expect(page.getByRole('heading', { name:'How the data reaches the map', exact:true })).toBeVisible();
  await expect(page.getByRole('heading', { name:'Animals Killed Since You Opened This Page', exact:true })).toBeAttached();
  await expect(page.getByRole('main')).toHaveCount(1);
  await expect(page.getByRole('navigation', { name:'Primary' }).getByRole('link')).toHaveText(['Map','Data','Contribute','About']);
  await expect(page.getByRole('navigation', { name:'Primary' }).getByRole('link', { name:'About', exact:true })).toHaveAttribute('aria-current','page');
  await expect(page.getByRole('link', { name:'Contribute to the project', exact:true })).toHaveAttribute('href','#/contribute?map=' + encodeURIComponent(map));
});

test('legacy methodology and Help aliases land in their corresponding About sections', async ({ page }) => {
  for (const [path, section] of [['methodology','technology'],['about/sources','technology'],['about/faq','records'],['about/help','help']] as const) {
    await page.goto('./#/' + path);
    await expect.poll(() => new URL(page.url()).hash).toBe('#/about?section=' + section);
    await expect(page.locator('.about-page .faq-page')).toBeVisible();
  }
});
