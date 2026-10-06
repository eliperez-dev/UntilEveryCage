import { expect, test, type Page } from '@playwright/test';

function operation(page: Page, path: string) {
  return page.locator('.opblock').filter({ has: page.locator('.opblock-summary-path').filter({ hasText: new RegExp(`^${path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`) }) });
}
async function isolatedPage(page: Page) {
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  await page.route('https://server.arcgisonline.com/**', route => route.abort());
}

test('Help provides written guides and a real, accessible local silent tutorial', async ({ page }) => {
  await isolatedPage(page);
  await page.goto('./#/about/help?map=%23%2Fmap%3Ff1a%3Dfield');
  await expect(page.getByRole('heading', { name: 'Help', exact: true })).toBeVisible();
  const video = page.locator('video');
  await expect(video).toHaveAttribute('controls', '');
  await expect(video).not.toHaveAttribute('autoplay');
  await expect(video).toHaveAttribute('aria-describedby', 'tutorial-caption');
  await expect(page.getByText('The steps above describe the same actions.', { exact: false })).toBeVisible();
  await expect.poll(() => video.evaluate(element => (element as HTMLVideoElement).readyState)).toBeGreaterThanOrEqual(1);
  const duration = await video.evaluate(element => (element as HTMLVideoElement).duration);
  expect(duration).toBeGreaterThan(5); expect(duration).toBeLessThan(30);
  await expect(page.getByRole('link', { name: 'Check status', exact: true })).toHaveAttribute('href', /map=%23%2Fmap%3Ff1a%3Dfield/);
  await expect(page.getByRole('link', { name: 'API documentation', exact: true })).toBeVisible();
});

test('Swagger is local and lazy, renders real GET operations and executes only on request', async ({ page, baseURL }) => {
  await isolatedPage(page);
  let writes = 0; let reads = 0; let swaggerAssets = 0;
  const external: string[] = [];
  const allowedOrigin = new URL(baseURL ?? 'http://127.0.0.1:4173/v2-preview/').origin;
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.includes('swagger-ui')) swaggerAssets += 1;
    if (url.protocol.startsWith('http') && url.origin !== allowedOrigin) external.push(url.origin);
  });
  await page.route('**/api/**', async route => {
    if (!new URL(route.request().url()).pathname.startsWith('/api/')) { await route.fallback(); return; }
    if (route.request().method() !== 'GET') writes += 1; else reads += 1;
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ api_version: 'v2', data: [], meta: { profile: 'official', next_cursor: null } }) });
  });
  await page.goto('./#/about');
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
  expect(swaggerAssets).toBe(0);
  await page.getByRole('button', { name: 'Database', exact: true }).click();
  await page.locator('#shared-database-nav').getByRole('link', { name: 'API documentation' }).click();
  await expect(page.locator('.opblock')).toHaveCount(10);
  await expect(page.locator('.opblock-summary-method')).toHaveText(Array(10).fill('GET'));
  expect(reads).toBe(0); expect(writes).toBe(0);
  await expect(page.locator('.topbar')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Authorize', exact: true })).toHaveCount(0);
  const list = operation(page, '/api/v2/locations');
  await list.locator('.opblock-summary-control').click();
  await list.getByRole('button', { name: 'Try it out', exact: true }).click();
  await list.getByRole('button', { name: 'Execute', exact: true }).click();
  await expect(list.locator('.responses-inner')).toContainText('200');
  expect(reads).toBe(1); expect(writes).toBe(0); expect(external).toEqual([]);
  expect(new URL(page.url()).hash).toMatch(/^#\/(?:about|database)\/api$/);
  await expect(page.getByRole('link', { name: 'Curated CSV (up to 1,000 records)' })).toHaveAttribute('href', '/api/v2/locations.csv?profile=official');
});

test('a community warning precedes execution and remains with a displayed community response', async ({ page }) => {
  await isolatedPage(page);
  await page.route('**/api/v2/locations?**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ api_version: 'v2', data: [], meta: { profile: 'community', next_cursor: null } }) }));
  await page.goto('./#/about/api');
  const list = operation(page, '/api/v2/locations');
  await list.locator('.opblock-summary-control').click();
  await list.getByRole('button', { name: 'Try it out', exact: true }).click();
  const profile = list.locator('tr').filter({ has: page.locator('.parameter__name').filter({ hasText: /^profile/ }) }).locator('select');
  await profile.selectOption('community');
  const warning = page.getByText('Unreviewed community claim — not verified by Until Every Cage.', { exact: true });
  await expect(warning).toBeVisible();
  await list.getByRole('button', { name: 'Execute', exact: true }).click();
  await expect(list.locator('.responses-inner')).toContainText('"community"');
  await profile.selectOption('official');
  await expect(warning).toBeVisible();
  await expect(list.locator('.responses-inner')).toContainText('"community"');
});

test('Help and expanded API paths stay usable on mobile without changing the masthead', async ({ page }) => {
  await isolatedPage(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./#/about/api');
  await expect(page.locator('.opblock')).toHaveCount(10);
  const list = operation(page, '/api/v2/locations');
  await list.locator('.opblock-summary-control').click();
  await list.getByRole('button', { name: 'Try it out', exact: true }).click();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'About', exact: true }).click();
  await page.locator('#shared-about-nav').getByRole('link', { name: 'Help' }).click();
  await expect(page.getByRole('heading', { name: 'Help', exact: true })).toBeVisible();
  await expect(page.getByRole('banner')).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('evidence explains existing records and validates an edited prefill before sending', async ({ page }) => {
  test.skip(process.env.VITE_COMMUNITY_PILOT !== 'true', 'Requires local enabled intake.');
  const record = '27d7ef4b-39de-4d9f-bacc-4062f560321e';
  let writes = 0;
  await isolatedPage(page);
  await page.route('**/api/community/submissions', async route => {
    writes += 1;
    expect(route.request().postDataJSON().target_record_id).toBe(record);
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ submission_id: record, receipt_secret: 'synthetic-tutorial-test-receipt', status: 'received' }) });
  });
  await page.goto(`./#/contribute/evidence?target=${record}`);
  await expect(page.getByText('Choose a contribution type', { exact: true })).toBeVisible();
  await expect(page.getByText('Add evidence to an existing record. Your submission will be reviewed.', { exact: true })).toBeVisible();
  const reference = page.getByLabel('Record link or ID', { exact: true });
  await expect(reference).toHaveValue(record);
  await reference.fill('this is not a record link');
  await page.getByLabel('What did you find?').fill('Synthetic evidence explanation');
  await page.getByLabel(/I have permission to share/).check();
  await page.getByRole('button', { name: 'Send for review' }).click();
  await expect(page.getByRole('alert')).toHaveText('Enter the record link or ID from the record details.');
  expect(writes).toBe(0);
  await reference.fill(`https://example.test/v2-preview/#/records/${record}`);
  await page.getByRole('button', { name: 'Send for review' }).click();
  await expect(page.getByRole('heading', { name: 'Contribution received' })).toBeVisible();
  expect(writes).toBe(1);
});

test('conditional manifest GET preserves If-None-Match and handles 304 without changing routes', async ({ page }) => {
  await isolatedPage(page);
  let conditionalHeader: string | undefined;
  await page.route('**/api/v2/releases/manifest?**', async route => {
    conditionalHeader = route.request().headers()['if-none-match'];
    expect(route.request().method()).toBe('GET');
    expect(route.request().headers()).not.toHaveProperty('authorization');
    await route.fulfill({ status: 304, headers: { ETag: '"synthetic-etag"' } });
  });
  await page.goto('./#/about/api');
  const manifest = operation(page, '/api/v2/releases/manifest');
  await manifest.locator('.opblock-summary-control').click();
  await manifest.getByRole('button', { name: 'Try it out', exact: true }).click();
  const header = manifest.locator('tr').filter({ has: page.locator('.parameter__name').filter({ hasText: 'If-None-Match' }) }).locator('input');
  await header.fill('"synthetic-etag"');
  await manifest.getByRole('button', { name: 'Execute', exact: true }).click();
  await expect(manifest.locator('.responses-inner')).toContainText('304');
  expect(conditionalHeader).toBe('"synthetic-etag"');
  expect(new URL(page.url()).hash).toMatch(/^#\/(?:about|database)\/api$/);
});

test('explorer text remains readable and narrow parameters use the available page width', async ({ page }) => {
  await isolatedPage(page);
  await page.goto('./#/about/api');
  await expect(page.locator('.opblock')).toHaveCount(10);
  const list = operation(page, '/api/v2/locations');
  for (const width of [1440, 768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.locator('.opblock-tag svg path').first()).toHaveCSS('fill', 'rgb(213, 221, 210)');
    await list.locator('.opblock-summary').hover();
    for (const expanded of [false, true]) {
      if (expanded) await list.locator('.opblock-summary-control').click();
      const contrasts = await list.locator('.opblock-summary').evaluate(summary => {
        const channel = (value: number) => { const scaled = value / 255; return scaled <= .04045 ? scaled / 12.92 : ((scaled + .055) / 1.055) ** 2.4; };
        const luminance = (color: string) => { const rgb = color.match(/[\d.]+/g)!.slice(0, 3).map(Number); return channel(rgb[0]!) * .2126 + channel(rgb[1]!) * .7152 + channel(rgb[2]!) * .0722; };
        const background = luminance(getComputedStyle(summary.closest('.opblock')!).backgroundColor);
        return [...summary.querySelectorAll('.opblock-summary-path, .opblock-summary-description')].filter(element => getComputedStyle(element).display !== 'none').map(element => { const foreground = luminance(getComputedStyle(element).color); return (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05); });
      });
      for (const contrast of contrasts) expect(contrast).toBeGreaterThanOrEqual(4.5);
      if (expanded) await list.locator('.opblock-summary-control').click();
    }
  }
  await list.locator('.opblock-summary-control').click();
  const row = list.locator('tr').filter({ has: page.locator('.parameter__name').filter({ hasText: /^profile/ }) });
  const name = await row.locator('.parameters-col_name').boundingBox();
  const description = await row.locator('.parameters-col_description').boundingBox();
  expect(description!.y).toBeGreaterThan(name!.y);
  expect(Math.abs(name!.x - description!.x)).toBeLessThan(1);
  const api = await page.locator('.api-page').boundingBox();
  expect(api!.x).toBe(16); expect(api!.width).toBe(343);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.goto('./#/about/help');
  const help = await page.locator('.help-page').boundingBox();
  expect(help!.x).toBe(16); expect(help!.width).toBe(343);
});
