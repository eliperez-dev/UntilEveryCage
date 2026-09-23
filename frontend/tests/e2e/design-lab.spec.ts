import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const directions = ['atlas', 'index', 'field'] as const;

for (const direction of directions) {
  test(`${direction} shares the local review engine and preserves state when switching`, async ({ page }) => {
    const apiRequests: string[] = [];
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url()); });
    await page.goto(`./#/map?f1a=${direction}&scenario=dense`);
    await expect(page.locator('.lab[data-direction]')).toHaveAttribute('data-direction', direction);
    await expect(page.getByRole('searchbox').first()).toBeVisible();
    await expect(page.getByLabel('Location precision legend')).toContainText('Exact site');

    const search = page.getByRole('searchbox').first();
    await search.fill('Aarhus');
    expect(new URL(page.url()).hash).toContain('q=Aarhus');
    await search.fill('');

    const filters = page.locator('details').first();
    await filters.locator('summary').click();
    await page.getByLabel('Poultry', { exact: true }).check();
    expect(new URL(page.url()).hash).toContain('category=Poultry');
    await filters.locator('summary').click();
    await page.getByRole('button', { name: 'Pan map east' }).click();
    expect(new URL(page.url()).hash).toContain('lon=25');
    await page.getByRole('button', { name: 'Satellite' }).click();
    await expect(page.getByText(/Satellite imagery unavailable/)).toBeVisible();

    await page.getByRole('button', { name: /Cluster of 4 records near Aarhus/i }).click();
    await expect(page.getByText(/2 exact · 2 approximate/i)).toBeVisible();
    expect(new URL(page.url()).hash).toContain('cluster=aarhus');

    await page.locator('.record-list button').filter({ hasText: 'Synthetic Poultry record 01' }).click();
    expect(new URL(page.url()).hash).toContain('selected=syn-001');

    const nextDirection = direction === 'atlas' ? 'index' : direction === 'index' ? 'field' : 'atlas';
    const directionSelect = direction === 'field'
      ? page.locator('.review-tools').getByLabel('Direction')
      : page.locator('.lab-header').getByLabel('Direction');
    await directionSelect.selectOption(nextDirection);
    const hash = new URL(page.url()).hash;
    for (const value of [`f1a=${nextDirection}`, 'scenario=dense', 'selected=syn-001', 'category=Poultry', 'cluster=aarhus', 'lon=25', 'basemap=satellite']) expect(hash).toContain(value);
    await expect(page.locator('.lab[data-direction]')).toHaveAttribute('data-direction', nextDirection);
    await expect(page.getByText(/Satellite imagery unavailable/)).toBeVisible();
    await expect(page.getByText(/2 exact · 2 approximate/i)).toBeVisible();
    expect(apiRequests).toEqual([]);
  });
}

test('unmapped records remain semantic list entries and never become map controls', async ({ page }) => {
  await page.goto('./#/map?f1a=index');
  await expect(page.getByRole('button', { name: /record 04.*unmapped/i })).toBeVisible();
  await expect(page.getByLabel(/Provisional map showing synthetic facility records/).getByRole('button', { name: /record 04/i })).toHaveCount(0);
});

for (const direction of directions) {
  test(`${direction} announces scenario states and fits narrow or zoomed layouts`, async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 780 });
    await page.goto(`./#/map?f1a=${direction}`);
    await expect(page.locator('.lab[data-direction]')).toHaveAttribute('data-direction', direction);
    const accessibility = await new AxeBuilder({ page }).analyze();
    expect(accessibility.violations.map(violation => ({ id: violation.id, help: violation.help, nodes: violation.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) }))).toEqual([]);

    const controls = direction === 'field'
      ? page.locator('.review-tools').getByLabel('Scenario')
      : page.locator('.lab-header').getByLabel('Scenario');
    await controls.selectOption('loading');
    await expect(page.getByRole('status').first()).toContainText(/Loading|Assembling/);
    await controls.selectOption('empty');
    await expect(page.getByText(/No matching records|No eligible|no synthetic records/i).first()).toBeVisible();
    await controls.selectOption('error');
    await expect(page.getByRole('alert').first()).toContainText(/No live fallback was attempted|No live source was queried/);

    await controls.selectOption('default');
    const narrowWidth = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    expect(narrowWidth.scroll).toBeLessThanOrEqual(narrowWidth.client + 1);
    await page.setViewportSize({ width: 160, height: 780 });
    const zoomedWidth = await page.evaluate(() => ({
      client: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
      offenders: [...document.querySelectorAll<HTMLElement>('*')].map(element => ({ element, rect: element.getBoundingClientRect() })).filter(({ rect }) => rect.right > document.documentElement.clientWidth + 1).slice(0, 8).map(({ element, rect }) => `${element.tagName}.${String(element.className)}: ${Math.round(rect.left)}..${Math.round(rect.right)}`),
    }));
    expect(zoomedWidth.scroll, JSON.stringify(zoomedWidth.offenders)).toBeLessThanOrEqual(zoomedWidth.client + 1);
  });
}
