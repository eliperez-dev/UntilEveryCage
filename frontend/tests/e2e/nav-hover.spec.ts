import { expect, test, type BrowserContext, type Page } from '@playwright/test';

async function isolate(context: BrowserContext) {
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.protocol.startsWith('http') && !['localhost', '127.0.0.1'].includes(url.hostname)) return route.abort();
    if (url.pathname.startsWith('/api/')) return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
    if (url.pathname.startsWith('/dev/real-preview/')) return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ api_version: 'real-preview-v1', data: [], meta: { private_preview: true, next_cursor: null } }) });
    if (url.pathname === '/v2-preview/') {
      const response = await route.fetch();
      return route.fulfill({ response, body: (await response.text()).replace(/<meta name="uec-local-data-mode" content="real-preview">/g, '') });
    }
    return route.fallback();
  });
}

test.beforeEach(async ({ context }) => isolate(context));

test('the masthead exposes five direct destinations and Tools', async ({ page }) => {
  await page.goto('./#/about');
  const nav = page.getByRole('navigation', { name: 'Primary' });
  await expect(nav.getByRole('link')).toHaveText(['Map', 'Database', 'API', 'Contribute', 'About']);
  await expect(page.getByRole('button', { name: 'Tools', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /Show (About|Database) pages/ })).toHaveCount(0);
  await expect(page.locator('#shared-about-nav, #shared-database-nav')).toHaveCount(0);
  await nav.getByRole('link', { name: 'API', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'API and data access' })).toBeVisible();
  await nav.getByRole('link', { name: 'About', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Until every cage is empty' })).toBeVisible();
});

test('direct links retain native keyboard and browser navigation', async ({ page, context }) => {
  await page.goto('./#/about/faq');
  const database = page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database', exact: true });
  await database.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Browse records', exact: true })).toBeVisible();
  const popupPromise = context.waitForEvent('page');
  await database.click({ modifiers: ['Control'] });
  const popup = await popupPromise;
  await popup.waitForLoadState('domcontentloaded');
  await expect(popup.getByRole('heading', { name: 'Browse records', exact: true })).toBeVisible();
  await popup.close();
});

test('compact direct navigation remains usable on a narrow touch screen', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 375, height: 844 }, isMobile: true, hasTouch: true });
  await isolate(context);
  const page = await context.newPage();
  await page.goto('./#/about');
  for (const label of ['Map', 'Database', 'API', 'Contribute', 'About']) {
    await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: label, exact: true })).toBeVisible();
  }
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'API', exact: true }).tap();
  await expect(page.getByRole('heading', { name: 'API and data access' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await context.close();
});
