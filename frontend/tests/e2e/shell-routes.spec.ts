import { test, expect } from '@playwright/test';

const routeTail = (page: import('@playwright/test').Page, tail: string) =>
  expect(new URL(page.url()).hash).toBe(`#/${tail}`);

test('the shared shell exposes the primary map and database routes', async ({ page }) => {
  await page.goto('./#/map');
  await expect(page.getByRole('banner')).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: /map/i })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database' })).toBeVisible();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database' }).click();
  await routeTail(page, 'database');
  await expect(page.getByRole('heading', { level: 1, name: /database/i })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Map' })).toBeVisible();
});

test('a record URL is directly addressable and has a route-specific heading', async ({ page }) => {
  await page.goto('./#/records/synthetic-record-1');
  await expect(new URL(page.url()).hash).toBe('#/records/synthetic-record-1');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database' })).toBeVisible();
});

test('the shell keeps route context in the URL through back and forward navigation', async ({ page }) => {
  await page.goto('./#/map?profile=community&query=synthetic');
  await expect(page.getByRole('heading', { level: 1, name: /map/i })).toBeVisible();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database' }).click();
  await routeTail(page, 'database');
  await expect.poll(() => new URL(page.url()).hash).toBe('#/database');
  await page.goBack();
  await expect.poll(() => new URL(page.url()).hash).toBe('#/map?profile=community&query=synthetic');
  await page.goForward();
  await routeTail(page, 'database');
});

test('About contains the sources & methodology page and returns via browser history', async ({ page }) => {
  await page.goto('./#/database');
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'About', exact: true }).click();
  await page.locator('#shared-about-nav').getByRole('link', { name: 'Overview' }).click();
  await expect.poll(() => new URL(page.url()).hash).toBe('#/about');
  await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible();
  await page.getByRole('button', { name: 'About', exact: true }).click();
  await page.locator('#shared-about-nav').getByRole('link', { name: 'Sources & methodology' }).click();
  await expect.poll(() => new URL(page.url()).hash).toBe('#/about/sources');
  await expect(page.getByRole('heading', { level: 1, name: 'Sources & Methodology' })).toBeVisible();
  await expect(page.getByText('A centroid is', { exact: false })).toBeVisible();
  await expect(page.getByText('Maps use OpenStreetMap tiles', { exact: false })).toBeVisible();
  await expect(page.getByRole('link', { name: 'untileverycageproject@protonmail.com' })).toHaveAttribute('href', 'mailto:untileverycageproject@protonmail.com');
  await page.goBack();
  await expect.poll(() => new URL(page.url()).hash).toBe('#/about');
});

test('the Contribute hub, bug report, and About pages share the primary navigation', async ({ page }) => {
  await page.goto('./#/contribute');
  const nav = page.getByRole('navigation', { name: 'Primary' });
  for (const label of ['Map', 'Database', 'Contribute']) await expect(nav.getByRole('link', { name: label })).toBeVisible();
  await expect(nav.getByRole('button', { name: 'About', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Add a facility', level: 1 })).toBeVisible();
  await page.getByRole('navigation', { name: 'Contribution tasks' }).getByRole('link', { name: 'Bug report' }).click();
  await expect(page.getByRole('heading', { name: 'Report a bug' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Report a public issue on GitHub' })).toHaveAttribute('href', 'https://github.com/eliperez-dev/UntilEveryCage/issues/new');
  await page.goto('./#/about/manifesto');
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
  for (const label of ['Map', 'Database', 'Contribute']) await expect(nav.getByRole('link', { name: label })).toBeVisible();
  await expect(nav.getByRole('button', { name: 'About', exact: true })).toBeVisible();
});

test('bug reports prepare a user-controlled email draft without copying URL context', async ({ page }) => {
  await page.goto('./#/contribute/bug?map=%23%2Fmap%3Ff1a%3Dfield');
  await page.getByLabel('What happened?').fill('Synthetic display issue');
  await page.getByLabel('Steps to reproduce').fill('Open a synthetic page.');
  await page.getByRole('button', { name: 'Prepare email' }).click();
  const draft = page.getByRole('link', { name: 'Open email draft' });
  await expect(draft).toHaveAttribute('href', /^mailto:untileverycageproject@protonmail\.com/);
  const href = await draft.getAttribute('href');
  expect(decodeURIComponent(href ?? '')).toContain('Synthetic display issue');
  expect(decodeURIComponent(href ?? '')).not.toContain('f1a=field');
  await expect(page.getByRole('link', { name: 'Report a public issue on GitHub' })).toHaveAttribute('href', 'https://github.com/eliperez-dev/UntilEveryCage/issues/new');
});

test('a hash route remains a supported entry point for the same shell destinations', async ({ page }) => {
  await page.goto('./#/map');
  await expect(page.getByRole('heading', { level: 1, name: /map/i })).toBeVisible();
  await page.goto('./#/database');
  await expect(page.getByRole('heading', { level: 1, name: /database/i })).toBeVisible();
});

test('an unknown path exposes an accessible not-found state and a route back to the map', async ({ page }) => {
  await page.goto('./#/not-a-public-route');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Return to the map' })).toBeVisible();
});

test('route controls are focusable links with explicit destinations', async ({ page }) => {
  await page.goto('./#/map');
  await expect(page.getByRole('main')).toBeVisible();
  const mapLink = page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Map' });
  await mapLink.focus();
  await expect(mapLink).toBeFocused();
  await expect(mapLink).toHaveAttribute('href', '#/map');
  const databaseLink = page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database' });
  await databaseLink.focus();
  await expect(databaseLink).toBeFocused();
  await expect(databaseLink).toHaveAttribute('href', '#/database');
});

test('direct Contribute tasks, two About destinations, and code help are easy to find', async ({ page }) => {
  await page.goto('./#/contribute');
  await expect(page.getByRole('heading', { level: 1, name: 'Add a facility' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Contribute menu' })).toHaveCount(0);
  await expect(page.getByLabel('Contribution type')).toHaveCount(0);
  const tasks = page.getByRole('navigation', { name: 'Contribution tasks' });
  await expect(tasks.getByRole('link')).toHaveCount(6);
  await expect(tasks.getByRole('link', { name: 'Facility', exact: true })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('link', { name: 'Check status', exact: true })).toHaveAttribute('href', '#/contribution-status');
  await expect(page.getByRole('link', { name: 'Community submissions', exact: true })).toHaveAttribute('href', '#/community');
  await expect(page.getByRole('link', { name: 'Contribute code on GitHub' })).toHaveAttribute('href', 'https://github.com/eliperez-dev/UntilEveryCage');
  const about = page.getByRole('button', { name: 'About', exact: true });
  await expect(about).toHaveText('About');
  await about.click();
  await expect(page.locator('#shared-about-nav').getByRole('link')).toHaveCount(2);
  await expect(page.getByRole('link', { name: 'Manifesto', exact: true })).toHaveCount(0);
  await page.locator('#shared-about-nav').getByRole('link', { name: 'Overview' }).click();
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
  await expect(page.getByText('Make the hidden visible.', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Contribute code on GitHub' })).toHaveAttribute('href', 'https://github.com/eliperez-dev/UntilEveryCage');
  const overview = await page.locator('.about-page').innerText();
  await page.goto('./#/about/manifesto');
  await expect(page.locator('.about-page')).toHaveText(overview);
  await expect(page.getByRole('main')).toHaveCount(1);
});
