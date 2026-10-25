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

test('the masthead exposes six direct destinations and Tools', async ({ page }) => {
  await page.goto('./#/about');
  const nav = page.getByRole('navigation', { name: 'Primary' });
  await expect(nav.getByRole('link')).toHaveText(['Map', 'Database', 'API', 'Contribute', 'About', 'FAQ']);
  await expect(page.getByRole('button', { name: 'Tools', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /Show (About|Database) pages/ })).toHaveCount(0);
  await expect(page.locator('#shared-about-nav, #shared-database-nav')).toHaveCount(0);
  await nav.getByRole('link', { name: 'API', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'API and data access' })).toBeVisible();
  await nav.getByRole('link', { name: 'About', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty' })).toBeVisible();
  await nav.getByRole('link', { name: 'FAQ', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Frequently asked questions' })).toBeVisible();
});

test('direct links retain native keyboard and browser navigation', async ({ page, context }, testInfo) => {
  const mapContext = '#/map?lat=44.5&lon=8.1&z=5&basemap=satellite&release_id=synthetic-release';
  await page.goto(`./#/about/faq?map=${encodeURIComponent(mapContext)}`);
  const database = page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database', exact: true });
  await database.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Browse records', exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('heading', { name: 'Frequently asked questions', exact: true })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole('heading', { name: 'Browse records', exact: true })).toBeVisible();
  const about = page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'About', exact: true });
  const popupPromise = context.waitForEvent('page');
  // Use the native new-tab modifier: headless Linux middle-click handling is
  // inconsistent. Do not replace this with window.open or a scripted goto.
  await about.click({ modifiers: ['ControlOrMeta'] });
  const popup = await popupPromise;
  const pageErrors: string[] = [];
  const failedResources: string[] = [];
  popup.on('pageerror', error => pageErrors.push(error.message));
  popup.on('requestfailed', request => {
    const url = new URL(request.url());
    failedResources.push(`${request.method()} ${url.origin}${url.pathname}: ${request.failure()?.errorText ?? 'request failed'}`);
  });
  popup.on('response', response => {
    if (response.status() >= 400) {
      const url = new URL(response.url());
      failedResources.push(`${response.status()} ${url.origin}${url.pathname}`);
    }
  });
  try {
    // Native new tabs may be backgrounded and some engines defer their app load.
    await popup.bringToFront();
    await expect(popup).toHaveURL(/#\/about(?:$|[/?])/);
    await popup.waitForLoadState('domcontentloaded', { timeout: 10_000 });
    await expect(popup.getByRole('heading', { name: 'About Until Every Cage is Empty', exact: true })).toBeVisible();
    expect(new URL(popup.url()).hash).toContain(`map=${encodeURIComponent(mapContext)}`);
  } catch (error) {
    const diagnostics = {
      url: popup.url(),
      title: await popup.title().catch(() => '[unavailable]'),
      readyState: await popup.evaluate(() => document.readyState).catch(() => '[unavailable]'),
      bodyText: await popup.locator('body').innerText({ timeout: 1_000 }).catch(() => '[body unavailable]'),
      pageErrors,
      failedResources,
      assertion: error instanceof Error ? error.message : String(error),
    };
    await testInfo.attach('native-new-tab-diagnostics.json', {
      body: JSON.stringify(diagnostics, null, 2),
      contentType: 'application/json',
    });
    throw error;
  } finally {
    await popup.close().catch(() => {});
  }
});

test('compact direct navigation remains usable on a narrow touch screen', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 375, height: 844 }, isMobile: true, hasTouch: true });
  await isolate(context);
  const page = await context.newPage();
  await page.goto('./#/about');
  for (const label of ['Map', 'Database', 'API', 'Contribute', 'About', 'FAQ']) {
    await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: label, exact: true })).toBeVisible();
  }
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'API', exact: true }).tap();
  await expect(page.getByRole('heading', { name: 'API and data access' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await context.close();
});
