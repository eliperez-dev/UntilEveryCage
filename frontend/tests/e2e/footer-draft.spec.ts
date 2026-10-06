import { expect, test, type BrowserContext } from '@playwright/test';

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

test('the disclosure and credits preserve data context and appear once per non-map surface', async ({ page, context }) => {
  await isolate(context);
  const map = '#/map?f1a=field&list=closed';
  const suffix = `?map=${encodeURIComponent(map)}`;
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page.goto(`./#/about/faq${suffix}`);
  const footer = page.getByRole('contentinfo', { name: 'Project information' });
  await expect(footer).toHaveCount(1);
  await expect(footer).toContainText('An independent, open-source project.');
  await expect(footer).toContainText('Records may be incomplete or out of date. Inclusion does not establish current operation or wrongdoing.');
  await expect(footer).toContainText('Original website inspired by Final Nail.');
  await expect(footer.getByRole('navigation')).toHaveCount(0);
  await expect(footer.getByRole('link')).toHaveCount(5);
  const destinations = [
    ['Get in touch', 'mailto:untileverycageproject@protonmail.com'],
    ['support its hosting and data work', 'https://ko-fi.com/untileverycageisempty'],
    ['AGPLv3 or later', 'https://www.gnu.org/licenses/agpl-3.0.html'],
    ['Final Nail', 'https://finalnail.com/'],
  ];
  for (const [name, href] of destinations) {
    const link = footer.getByRole('link', { name, exact: true });
    await expect(link).toHaveAttribute('href', href);
    if (!href.startsWith('mailto:')) { await expect(link).toHaveAttribute('target', '_blank'); await expect(link).toHaveAttribute('rel', 'noreferrer'); }
  }
  const data = footer.getByRole('link', { name: 'reuse terms' });
  await expect(data).toHaveAttribute('href', `#/database/downloads${suffix}`);
  const contact = footer.getByRole('link', { name: 'Get in touch' });
  await contact.focus(); await expect(contact).toBeFocused();
  expect(await contact.evaluate(element => getComputedStyle(element).outlineStyle)).toBe('solid');
  await page.keyboard.press('Tab');
  await expect(footer.getByRole('link', { name: 'support its hosting and data work' })).toBeFocused();
  await page.screenshot({ path: '../target/footer-copy-desktop-1440.png', fullPage: true });
  await data.click();
  await expect(page.getByRole('heading', { name: 'Downloads', exact: true })).toBeVisible();
  await expect(footer).toHaveCount(1);
  expect(new URL(page.url()).hash).toContain(`map=${encodeURIComponent(map)}`);
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Map', exact: true })).toHaveAttribute('href', map);
  for (const route of ['about', 'about/sources', 'contribute/bug', 'database', 'records/synthetic-record']) {
    await page.goto(`./#/${route}`); await expect(footer).toHaveCount(1);
  }
  await page.goto('./#/map'); await expect(footer).toHaveCount(0);
});

test('touch disclosure wraps readably at 375px and 320px and data terms remain usable', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 375, height: 844 }, isMobile: true, hasTouch: true });
  await isolate(context);
  const page = await context.newPage();
  await page.goto('./#/about/faq');
  const footer = page.getByRole('contentinfo', { name: 'Project information' });
  for (const width of [375, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await footer.scrollIntoViewIfNeeded();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const link of await footer.getByRole('link').all()) {
      await expect(link).toBeVisible();
      const rects = await link.evaluate(element => Array.from(element.getClientRects()).map(rect => ({ left: rect.left, right: rect.right })));
      for (const rect of rects) { expect(rect.left).toBeGreaterThanOrEqual(0); expect(rect.right).toBeLessThanOrEqual(width); }
      expect(await link.evaluate(element => parseFloat(getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(13);
    }
    if (width === 375) await page.screenshot({ path: '../target/footer-copy-touch-375.png', fullPage: false });
  }
  await footer.getByRole('link', { name: 'reuse terms' }).tap();
  await expect(page.getByRole('heading', { name: 'Downloads', exact: true })).toBeVisible();
  await expect(footer).toHaveCount(1);
  await context.close();
});
