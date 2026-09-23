import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('shared design lab stays local and preserves state across direction changes', async ({ page }) => {
  const apiRequests: string[] = [];
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url()); });
  await page.goto('./#/map?f1a=atlas&scenario=dense&selected=syn-042&q=synthetic&lat=40&lon=-12&z=5');
  await expect(page.getByText('Synthetic development data · not a release')).toBeVisible();
  await expect(page.getByRole('region', { name: /provisional map/i })).toBeVisible();
  await expect(page.getByLabel('Location precision legend')).toContainText('Exact site');
  await page.getByLabel('Direction').selectOption('field');
  const hash = new URL(page.url()).hash;
  expect(hash).toContain('f1a=field');
  for (const value of ['scenario=dense', 'selected=syn-042', 'q=synthetic', 'lat=40', 'lon=-12', 'z=5']) expect(hash).toContain(value);
  expect(apiRequests).toEqual([]);
});

test('unmapped records remain in the list and never become map controls', async ({ page }) => {
  await page.goto('./#/map?f1a=index&q=record+04');
  await expect(page.getByRole('button', { name: /record 04.*unmapped/i })).toBeVisible();
  await expect(page.getByRole('region', { name: /provisional map/i }).getByRole('button', { name: /record 04/i })).toHaveCount(0);
});

test('filters, list visibility, viewport, and cluster expansion are URL-backed actions', async ({ page }) => {
  await page.goto('./#/map?f1a=atlas');
  await page.locator('.lab-filters summary').click();
  await expect(page.getByLabel('Poultry', { exact: true })).toBeVisible();
  await page.getByLabel('Poultry', { exact: true }).check();
  await expect(page.getByRole('heading', { name: /synchronized records/i })).toContainText('16');
  expect(new URL(page.url()).hash).toContain('category=Poultry');
  await page.getByRole('button', { name: 'Hide synchronized list' }).click();
  await expect(page.getByRole('region', { name: /synchronized records/i })).toBeHidden();
  expect(new URL(page.url()).hash).toContain('list=closed');
  await page.getByRole('button', { name: 'Show synchronized list' }).click();
  await page.getByRole('button', { name: 'Pan map east' }).click();
  expect(new URL(page.url()).hash).toContain('lon=25');
});

test('clusters disclose composition and satellite is honestly unavailable', async ({ page }) => {
  await page.goto('./#/map?f1a=field');
  await page.getByRole('button', { name: /cluster of 4 records near aarhus/i }).click();
  await expect(page.getByText(/2 exact · 2 approximate/i)).toBeVisible();
  await page.getByRole('button', { name: 'Satellite' }).click();
  await expect(page.getByRole('status')).toContainText(/Satellite imagery unavailable/);
});

test('mobile scenario and loading, empty, and error states remain explicit', async ({ page }) => {
  await page.goto('./#/map?f1a=atlas&scenario=mobile');
  await expect(page.locator('.lab')).toHaveAttribute('data-scenario', 'mobile');
  await page.goto('./#/map?f1a=atlas&scenario=loading');
  await expect(page.getByRole('status')).toContainText('Loading synthetic records');
  await page.goto('./#/map?f1a=atlas&scenario=empty');
  await expect(page.getByRole('status')).toContainText('No eligible synthetic records');
  await page.goto('./#/map?f1a=atlas&scenario=error');
  await expect(page.getByRole('alert')).toContainText('No live fallback was attempted');
});

test('keyboard access, automated accessibility, and narrow or zoomed layouts remain usable', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 780 });
  await page.goto('./#/map?f1a=atlas');
  await expect(page.getByText('Synthetic development data · not a release')).toBeVisible();
  await page.getByRole('searchbox').focus();
  await page.keyboard.press('Tab');
  await expect(page.locator('.lab-filters summary')).toBeFocused();
  const narrowWidth = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(narrowWidth.scroll).toBeLessThanOrEqual(narrowWidth.client + 1);
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.map(violation => ({ id: violation.id, help: violation.help, nodes: violation.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) }))).toEqual([]);
  await page.setViewportSize({ width: 160, height: 780 });
  const zoomedWidth = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
    offenders: [...document.querySelectorAll<HTMLElement>('*')].map(element => ({ element, rect: element.getBoundingClientRect() })).filter(({ rect }) => rect.right > document.documentElement.clientWidth + 1).slice(0, 8).map(({ element, rect }) => `${element.tagName}.${element.className}: ${Math.round(rect.left)}..${Math.round(rect.right)}`),
  }));
  expect(zoomedWidth.scroll, JSON.stringify(zoomedWidth.offenders)).toBeLessThanOrEqual(zoomedWidth.client + 1);
});
