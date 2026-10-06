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

test('the footer offers project and utility links, preserves context, and appears once', async ({ page, context }) => {
  await isolate(context);
  const map = '#/map?f1a=field&list=closed';
  const suffix = `?map=${encodeURIComponent(map)}`;
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page.goto(`./#/about/faq${suffix}`);
  const footer = page.getByRole('contentinfo', { name: 'Project information' });
  await expect(footer).toHaveCount(1);
  await expect(footer.getByText('An independent, open-source project.', { exact: true })).toBeVisible();
  const project = footer.getByRole('navigation', { name: 'Project links' });
  const destinations = [
    ['Contact', 'mailto:untileverycageproject@protonmail.com'],
    ['Support on Ko-fi', 'https://ko-fi.com/untileverycageisempty'],
    ['GitHub', 'https://github.com/eliperez-dev/UntilEveryCage'],
    ['Discord', 'https://discord.gg/wbdTHzAZ4b'],
    ['Resources', 'https://linktr.ee/veganresource'],
  ];
  for (const [name, href] of destinations) {
    const link = project.getByRole('link', { name, exact: true });
    await expect(link).toHaveAttribute('href', href);
    if (!href.startsWith('mailto:')) { await expect(link).toHaveAttribute('target', '_blank'); await expect(link).toHaveAttribute('rel', 'noreferrer'); }
  }
  const utilities = footer.getByRole('navigation', { name: 'Help and feedback' });
  const routes = [['Help', 'about/help'], ['Report a bug', 'contribute/bug'], ['Privacy or removal', 'contribute/privacy-removal'], ['Sources & methodology', 'about/sources']];
  for (const [name, path] of routes) await expect(utilities.getByRole('link', { name, exact: true })).toHaveAttribute('href', `#/${path}${suffix}`);
  await expect(footer.getByRole('link', { name: 'AGPLv3 or later' })).toHaveAttribute('href', 'https://www.gnu.org/licenses/agpl-3.0.html');
  await expect(footer.getByRole('link', { name: 'reuse terms' })).toHaveAttribute('href', `#/database/downloads${suffix}`);
  const help = utilities.getByRole('link', { name: 'Help', exact: true });
  await help.focus(); await expect(help).toBeFocused();
  expect(await help.evaluate(element => getComputedStyle(element).outlineStyle)).toBe('solid');
  await page.screenshot({ path: '../target/footer-draft-desktop-1440.png', fullPage: true });
  for (const [name] of routes) {
    await utilities.getByRole('link', { name, exact: true }).click();
    await expect(footer).toHaveCount(1);
    expect(new URL(page.url()).hash).toContain(`map=${encodeURIComponent(map)}`);
    await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Map', exact: true })).toHaveAttribute('href', map);
  }
  await footer.getByRole('link', { name: 'reuse terms' }).click();
  await expect(page.getByRole('heading', { name: 'Downloads', exact: true })).toBeVisible();
  await page.goto('./#/database'); await expect(footer).toHaveCount(1);
  await page.goto('./#/records/synthetic-record'); await expect(footer).toHaveCount(1);
  await page.goto('./#/map'); await expect(footer).toHaveCount(0);
});

test('touch footer links wrap at 375px and 320px with usable targets', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 375, height: 844 }, isMobile: true, hasTouch: true });
  await isolate(context);
  const page = await context.newPage();
  await page.goto('./#/about/faq');
  const footer = page.getByRole('contentinfo', { name: 'Project information' });
  for (const width of [375, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await footer.scrollIntoViewIfNeeded();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const link of await footer.getByRole('navigation').getByRole('link').all()) {
      await expect(link).toBeVisible();
      const box = (await link.boundingBox())!;
      expect(box.height).toBeGreaterThanOrEqual(44);
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width);
    }
    if (width === 375) await page.screenshot({ path: '../target/footer-draft-touch-375.png', fullPage: false });
  }
  await footer.getByRole('navigation', { name: 'Help and feedback' }).getByRole('link', { name: 'Report a bug' }).tap();
  await expect(page.getByRole('heading', { name: 'Report a bug', exact: true })).toBeVisible();
  await expect(footer).toHaveCount(1);
  await context.close();
});
