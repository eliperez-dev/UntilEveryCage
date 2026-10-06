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
const title = (page: Page, name: 'About' | 'Database') => page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name, exact: true });

test.beforeEach(async ({ context }) => isolate(context));

test('hover crosses the dropdown gap, submenu links navigate, and mouseleave dismisses', async ({ page }) => {
  await page.goto('./#/about/faq');
  const about = title(page, 'About');
  await expect(page.getByRole('button', { name: 'Show About pages' })).toBeHidden();
  await about.hover();
  const menu = page.locator('#shared-about-nav');
  await expect(menu).toBeVisible();
  expect(new URL(page.url()).hash).toBe('#/about/faq');
  await menu.getByRole('link', { name: 'FAQ', exact: true }).click();
  await expect(menu).toHaveCount(0);
  await about.hover();
  const parentBox = (await about.boundingBox())!;
  const menuBox = (await menu.boundingBox())!;
  const x = parentBox.x + parentBox.width / 2;
  await page.mouse.move(x, parentBox.y + parentBox.height - 1);
  await page.mouse.move(x, menuBox.y + 10, { steps: 12 });
  await expect(menu).toBeVisible();
  await menu.getByRole('link', { name: 'Help', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Help', exact: true })).toBeVisible();
  await expect(menu).toHaveCount(0);
  await about.hover();
  // Mouse focus must not keep the hover menu open after leaving its group.
  await page.mouse.down(); await page.mouse.up();
  await about.hover();
  await page.mouse.move(20, 250);
  await expect(menu).toHaveCount(0);
  const database = title(page, 'Database');
  await database.hover();
  await page.locator('#shared-database-nav').getByRole('link', { name: 'Downloads', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Downloads', exact: true })).toBeVisible();
  await database.hover();
  await page.mouse.click(20, 350);
  await expect(page.locator('#shared-database-nav')).toHaveCount(0);
});

test('parent anchors navigate defaults by click and Enter and retain native new-tab behavior', async ({ page, context }) => {
  await page.goto('./#/about/faq');
  const about = title(page, 'About');
  await expect(about).toHaveAttribute('href', '#/about');
  await about.click();
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  await expect(page.locator('#shared-about-nav')).toHaveCount(0);
  const database = title(page, 'Database');
  await expect(database).toHaveAttribute('href', '#/database');
  await database.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Browse records', exact: true })).toBeVisible();
  await about.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  const popupPromise = context.waitForEvent('page');
  await database.click({ modifiers: ['Control'] });
  const popup = await popupPromise;
  await popup.waitForLoadState();
  await expect(popup.getByRole('heading', { name: 'Browse records', exact: true })).toBeVisible();
  expect(new URL(popup.url()).hash).toBe('#/database');
  expect(new URL(page.url()).hash).toBe('#/about');
  await popup.close();
});

test('keyboard focus opens destinations, Tab traverses them, and Escape stays dismissed', async ({ page }) => {
  await page.goto('./#/about/faq');
  const database = title(page, 'Database');
  await title(page, 'About').focus();
  await page.keyboard.press('Escape');
  await database.focus();
  await expect(page.locator('#shared-database-nav')).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.locator('#shared-database-nav').getByRole('link', { name: 'Browse records' })).toBeFocused();
  // Leaving with the mouse must keep a menu open when its keyboard focus remains.
  await database.hover();
  await page.mouse.move(20, 250);
  await expect(page.locator('#shared-database-nav')).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.locator('#shared-database-nav').getByRole('link', { name: 'Downloads', exact: true })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(database).toBeFocused();
  await expect(page.locator('#shared-database-nav')).toHaveCount(0);
  await page.keyboard.press('ArrowDown');
  await expect(page.locator('#shared-database-nav').getByRole('link', { name: 'Browse records' })).toBeFocused();
  await database.focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.locator('#shared-database-nav').getByRole('link', { name: 'Browse records' })).toBeFocused();
  await page.keyboard.press('Escape');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Contribute' })).toBeFocused();
  await expect(page.locator('#shared-database-nav')).toHaveCount(0);
  const about = title(page, 'About');
  await about.hover();
  await page.keyboard.press('Escape');
  await expect(about).toBeFocused();
  const box = (await about.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2 + 1, box.y + box.height / 2);
  await expect(page.locator('#shared-about-nav')).toHaveCount(0);
});

test('touch ellipses toggle subpages while title taps navigate defaults at 375px', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 375, height: 844 }, isMobile: true, hasTouch: true });
  await isolate(context);
  const page = await context.newPage();
  await page.goto('./#/about/faq');
  const about = title(page, 'About');
  const showAbout = page.getByRole('button', { name: 'Show About pages' });
  const showDatabase = page.getByRole('button', { name: 'Show Database pages' });
  for (const button of [showAbout, showDatabase]) {
    await expect(button).toBeVisible();
    const box = (await button.boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(44); expect(box.height).toBeGreaterThanOrEqual(44);
  }
  await showAbout.tap(); await expect(page.locator('#shared-about-nav')).toBeVisible();
  expect(new URL(page.url()).hash).toBe('#/about/faq');
  await showAbout.tap(); await expect(page.locator('#shared-about-nav')).toHaveCount(0);
  await about.tap(); await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
  await showAbout.tap();
  await page.locator('#shared-about-nav').getByRole('link', { name: 'FAQ', exact: true }).tap();
  await expect(page.getByRole('heading', { name: 'FAQ', exact: true })).toBeVisible();
  await title(page, 'Database').tap();
  await expect(page.getByRole('heading', { name: 'Browse records', exact: true })).toBeVisible();
  await showDatabase.tap();
  await page.locator('#shared-database-nav').getByRole('link', { name: 'Downloads', exact: true }).tap();
  await expect(page.getByRole('heading', { name: 'Downloads', exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await showAbout.tap();
  await expect(page.locator('#shared-about-nav')).toBeVisible();
  await expect(showAbout).toBeVisible();
  await page.screenshot({ path: '../target/nav-hover-touch-375.png', fullPage: false });
  await context.close();
});

test('desktop header retains the established compact styling', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto('./#/about/faq');
  await title(page, 'Database').hover();
  await expect(page.locator('#shared-database-nav')).toBeVisible();
  await page.screenshot({ path: '../target/nav-hover-desktop-1440.png', fullPage: true });
});


test('hybrid touch and mouse devices keep both input paths available', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 1280, height: 900 }, hasTouch: true });
  await isolate(context);
  const page = await context.newPage();
  await page.goto('./#/about/faq');
  await expect(page.getByRole('button', { name: 'Show About pages' })).toBeVisible();
  await title(page, 'About').hover();
  await expect(page.locator('#shared-about-nav')).toBeVisible();
  await page.mouse.move(20, 350);
  await expect(page.locator('#shared-about-nav')).toHaveCount(0);
  await page.getByRole('button', { name: 'Show About pages' }).tap();
  await expect(page.locator('#shared-about-nav')).toBeVisible();
  await context.close();
});
