import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', route => new URL(route.request().url()).pathname.startsWith('/api/') ? route.fulfill({ contentType: 'application/json', body: JSON.stringify({ api_version: 'v2', data: [], meta: { release_id: null, profile: 'official', coverage_note: 'No public release.' } }) }) : route.fallback());
  await page.route('**/dev/real-preview/**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ api_version: 'real-preview-v1', data: [], meta: { private_preview: true, next_cursor: null } }) }));
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  await page.route('https://server.arcgisonline.com/**', route => route.abort());
  await page.route('**/v2-preview/', async route => { const response = await route.fetch(); await route.fulfill({ response, body: (await response.text()).replace(/<meta name="uec-local-data-mode" content="real-preview">/g, '') }); });
});

const routePath = (page: import('@playwright/test').Page) =>
  new URL(`http://test${new URL(page.url()).hash.slice(1)}`);

const expectRoute = async (page: import('@playwright/test').Page, pathname: string) =>
  expect(routePath(page).pathname).toBe(pathname);

test('the shared shell exposes the primary map and database routes', async ({ page }) => {
  await page.goto('./#/map');
  await expect(page.getByRole('banner')).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: /map/i })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database', exact: true })).toBeVisible();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database', exact: true }).click();
  await expectRoute(page, '/database');
  expect(routePath(page).searchParams.get('lat')).toBe('45');
  expect(routePath(page).searchParams.get('lon')).toBe('5');
  expect(routePath(page).searchParams.get('z')).toBe('2');
  await expect(page.getByRole('heading', { level: 1, name: /Browse records/i })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Map' })).toBeVisible();
});

test('centered primary navigation and map controls stay aligned across desktop and mobile', async ({ page }) => {
  await page.route('**/api/v2/releases/manifest?**', route => route.fulfill({ contentType:'application/json', body:JSON.stringify({ api_version:'v2', data:{ release_id:'synthetic-release', profile:'official', manifest:{}, manifest_sha256:'a'.repeat(64), suppression_generation:1 } }) }));
  await page.route('**/api/v2/locations?**', route => route.fulfill({ contentType:'application/json', body:JSON.stringify({ api_version:'v2', data:[], meta:{ release_id:'synthetic-release', ruleset_version:'synthetic-rules', profile:'official', next_cursor:null, coverage_note:'Synthetic release.' } }) }));
  await page.goto('./#/map');
  const nav = page.getByRole('navigation', { name: 'Primary' });
  await expect(nav.getByRole('link')).toHaveText(['Map','Database','API','Contribute','About','FAQ']);
  await expect(page.getByRole('button', { name: 'Search map' })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Map view' }).getByText('Right-mouse to rotate / Left-mouse to pan')).toBeVisible();
  const midpoint = async () => page.evaluate(() => {
    const rect = document.querySelector('nav[aria-label="Primary"]')!.getBoundingClientRect();
    return rect.left + rect.width / 2;
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect.poll(midpoint).toBeCloseTo(640, 0);
  const mapControlGeometry = async () => page.evaluate(() => {
    const search = document.querySelector('.search-toggle')!.getBoundingClientRect();
    const view = document.querySelector('.map-controls-wrap')!.getBoundingClientRect();
    return { left: search.left, right: innerWidth - view.right, overlap: search.right - view.left };
  });
  let inset = await mapControlGeometry();
  expect(Math.abs(inset.left - inset.right)).toBeLessThan(1);
  expect(inset.overlap).toBeLessThanOrEqual(0);
  const alignedStyles = await page.evaluate(() => {
    const search = getComputedStyle(document.querySelector('.search-toggle')!);
    const view = getComputedStyle(document.querySelector('.map-controls')!);
    return ['borderTopColor','backgroundColor','fontFamily','fontSize'].map(key => [search[key as keyof CSSStyleDeclaration], view[key as keyof CSSStyleDeclaration]]);
  });
  for (const [search, view] of alignedStyles) expect(search).toBe(view);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(nav.getByRole('link', { name: 'FAQ', exact: true })).toBeVisible();
  await expect.poll(midpoint).toBeCloseTo(195, 0);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  inset = await page.evaluate(() => {
    const search = document.querySelector('.search-toggle')!.getBoundingClientRect();
    const view = document.querySelector('.map-controls-wrap')!.getBoundingClientRect();
    return { left: search.left, right: innerWidth - view.right, overlap: search.right - view.left };
  });
  expect(Math.abs(inset.left - inset.right)).toBeLessThan(1);
  expect(inset.overlap).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 375, height: 812 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  inset = await mapControlGeometry();
  expect(Math.abs(inset.left - inset.right)).toBeLessThan(1);
  expect(inset.overlap).toBeLessThanOrEqual(0);
});

test('a record URL is directly addressable and has a route-specific heading', async ({ page }) => {
  await page.goto('./#/records/synthetic-record-1');
  await expect(new URL(page.url()).hash).toBe('#/records/synthetic-record-1');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database', exact: true })).toBeVisible();
});

test('the shell keeps map camera and style context in its Database return link', async ({ page }) => {
  await page.goto('./#/map?lat=44.5&lon=8.1&z=5&list=closed&basemap=satellite');
  await expect(page.getByRole('heading', { level: 1, name: /map/i })).toBeVisible();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database', exact: true }).click();
  await expectRoute(page, '/database');
  expect(routePath(page).searchParams.get('lat')).toBe('44.5');
  expect(routePath(page).searchParams.get('lon')).toBe('8.1');
  expect(routePath(page).searchParams.get('z')).toBe('5');
  expect(routePath(page).searchParams.get('basemap')).toBe('satellite');
  expect(routePath(page).searchParams.get('pitch')).toBeNull();
  // A closed rail is canonicalized by omitting `list`; only the open state is encoded.
  expect(routePath(page).searchParams.get('list')).not.toBe('open');
  expect(routePath(page).searchParams.get('basemap')).toBe('satellite');
  await page.goBack();
  await expect.poll(() => routePath(page).pathname).toBe('/map');
  await page.goForward();
  await expectRoute(page, '/database');
  expect(routePath(page).searchParams.get('basemap')).toBe('satellite');
});

test('direct Database URLs preserve only allowlisted map context in the explicit Map link', async ({ page }) => {
  await page.goto('./#/database?lat=38&lon=-96&z=4&pitch=27&bearing=14&basemap=satellite&list=open&release_id=release-2026-10&q=private%20search&profile=community&extra=unsafe');
  await expect(page.getByRole('heading', { level: 1, name: /Browse records/i })).toBeVisible();
  const mapLink = page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Map', exact: true });
  const href = await mapLink.getAttribute('href') ?? '';
  const mapDestination = new URL(`http://test/${href.slice(2)}`);
  expect(mapDestination.pathname).toBe('/map');
  for (const [key, value] of Object.entries({ lat: '38', lon: '-96', z: '4', pitch: '27', bearing: '14', basemap: 'satellite', list: 'open', release_id: 'release-2026-10' })) expect(mapDestination.searchParams.get(key)).toBe(value);
  expect(mapDestination.searchParams.has('q')).toBe(false);
  expect(mapDestination.searchParams.has('profile')).toBe(false);
  expect(mapDestination.searchParams.has('extra')).toBe(false);
  await mapLink.click();
  await expectRoute(page, '/map');
  expect(routePath(page).searchParams.get('lat')).toBe('38');
  expect(routePath(page).searchParams.get('pitch')).toBe('27');
  expect(routePath(page).searchParams.get('bearing')).toBe('14');
  expect(routePath(page).searchParams.get('basemap')).toBe('satellite');
  expect(routePath(page).searchParams.get('q')).toBeNull();
});

test('About and FAQ pages keep legacy routes without obsolete source/method content', async ({ page }) => {
  await page.goto('./#/database');
  const aboutLink = page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'About', exact: true });
  await aboutLink.click();
  await expect.poll(() => new URL(page.url()).hash).toBe('#/about');
  await expect(page.getByRole('heading', { level: 1, name: 'About Until Every Cage is Empty' })).toBeVisible();
  await page.goto('./#/about?section=sources');
  await expect.poll(() => new URL(page.url()).hash).toBe('#/about?section=sources');
  await expect(page.getByRole('heading', { level: 1, name: 'About Until Every Cage is Empty' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Sources and methods' })).toHaveCount(0);
  await expect(page.getByRole('article', { name: 'About Until Every Cage', exact: true }).getByRole('link', { name: 'Contact', exact: true })).toHaveAttribute('href', 'mailto:untileverycageproject@protonmail.com');
  await page.goto('./#/about/faq');
  await expect(page.getByRole('heading', { level: 1, name: 'Frequently asked questions' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'How the data reaches the map' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Sources and methods' })).toHaveCount(0);
  await expect(page.getByText(/sources and method are shown with the counter/i)).toHaveCount(0);
  await page.goto('./#/about/help');
  await expect(page.getByRole('heading', { level: 2, name: 'Help, support, and contact' })).toBeVisible();
  await page.goto('./#/methodology');
  await expect(page.getByRole('heading', { level: 2, name: 'How the data reaches the map' })).toBeVisible();
  await page.goBack();
});

test('the Contribute hub, bug report, and About pages share the primary navigation', async ({ page }) => {
  await page.goto('./#/contribute');
  const nav = page.getByRole('navigation', { name: 'Primary' });
  for (const label of ['Map', 'Contribute']) await expect(nav.getByRole('link', { name: label })).toBeVisible();
  await expect(nav.getByRole('link', { name: 'About', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Contribute to the project', level: 1 })).toBeVisible();
  await page.getByRole('link', { name: 'Report a bug', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Report a bug' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Report a public issue on GitHub' })).toHaveAttribute('href', 'https://github.com/eliperez-dev/UntilEveryCage/issues/new');
  await page.goto('./#/about/manifesto');
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty' })).toBeVisible();
  for (const label of ['Map', 'Contribute']) await expect(nav.getByRole('link', { name: label })).toBeVisible();
  await expect(nav.getByRole('link', { name: 'About', exact: true })).toBeVisible();
});

test('bug reports submit to the system without copying URL context', async ({ page }) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route('**/api/community/submissions', route => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ submission_id: '18c6ef3a-28cd-4c8e-a9bb-3951f45f210d', receipt_secret: 'synthetic-private-report-token', status: 'received' }) });
  });
  await page.goto('./#/contribute/bug?map=%23%2Fmap%3Ff1a%3Dfield');
  await page.getByLabel('What happened?').fill('Synthetic display issue');
  await page.getByLabel('Steps to reproduce').fill('Open a synthetic page.');
  await page.getByRole('button', { name: 'Send report', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Report saved.');
  expect(submitted).toEqual({ kind: 'bug', consent: true, description: 'Synthetic display issue', reproduction_steps: 'Open a synthetic page.' });
  await expect(page.getByRole('link', { name: 'Track report', exact: true })).toHaveAttribute('href', /^#\/contribution-status\?submission_id=/);
  await expect(page.getByRole('button', { name: 'Sent', exact: true })).toBeDisabled();
  await expect(page.getByRole('link', { name: 'Open email draft' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Report a public issue on GitHub' })).toHaveAttribute('href', 'https://github.com/eliperez-dev/UntilEveryCage/issues/new');
});

test('a failed bug submission keeps the form available for retry', async ({ page }) => {
  await page.route('**/api/community/submissions', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
  await page.goto('./#/contribute/bug');
  await page.getByLabel('What happened?').fill('Synthetic retry issue');
  await page.getByLabel('Steps to reproduce').fill('Synthetic steps');
  await page.getByRole('button', { name: 'Send report', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Could not send the report.');
  await expect(page.getByLabel('What happened?')).toHaveValue('Synthetic retry issue');
  await expect(page.getByRole('button', { name: 'Send report', exact: true })).toBeEnabled();
});

test('a hash route remains a supported entry point for the same shell destinations', async ({ page }) => {
  await page.goto('./#/map');
  await expect(page.getByRole('heading', { level: 1, name: /map/i })).toBeVisible();
  await page.goto('./#/database');
  await expect(page.getByRole('heading', { level: 1, name: /Browse records/i })).toBeVisible();
});

test('a cold contribution route recovers after its module import fails once', async ({ page }) => {
  const recordId = '4c4708fa-cdde-51dd-b7b9-30c907f7acce';
  let failedImport = false;
  let communityImportRequests = 0;
  page.on('request', request => { if (new URL(request.url()).pathname.includes('CommunityContributions')) communityImportRequests += 1; });
  await page.route('**/api/community/capabilities', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ enabled: true, types: ['facility', 'evidence', 'correction', 'duplicate', 'privacy_removal'] }) }));
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (!failedImport && /CommunityContributions(?:-[^/]+)?\.(?:svelte|js)$/.test(url.pathname)) {
      failedImport = true;
      return route.abort();
    }
    return route.fallback();
  });
  await page.goto(`./#/contribute/evidence?target=${recordId}`);
  await expect(page.getByRole('heading', { name: 'Unable to open this page' })).toBeVisible();
  await expect(page.getByText('The community pilot could not be opened.')).toBeVisible();
  await page.getByRole('button', { name: 'Reload to try again' }).click();
  await expect.poll(() => communityImportRequests).toBeGreaterThan(1);
  await expect(page.getByRole('heading', { name: 'Add evidence' })).toBeVisible();
  await expect(page.getByLabel('Record link or ID')).toHaveValue(recordId);
});

test('public map navigation links keep release and viewport context without fixture parameters', async ({ page }) => {
  const releaseId = 'release-2026-10-18';
  await page.route('**/v2-preview/', async route => {
    const response = await route.fetch();
    const html = (await response.text()).replace(/<meta name="uec-local-data-mode" content="[^"]*">/g, '');
    await route.fulfill({ response, body: html.replace('</head>', '<meta name="uec-local-data-mode" content="public-release"></head>') });
  });
  await page.route('**/api/v2/releases/manifest*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({
    api_version: 'v2', data: { profile: 'official', release_id: releaseId, manifest: {}, manifest_sha256: 'a'.repeat(64), suppression_generation: 0 },
  }) }));
  await page.goto(`./#/map?scenario=default&list=closed&lat=38&lon=-96&z=4&release_id=${releaseId}`);
  const mapHome = page.getByRole('link', { name: 'Until Every Cage map home' });
  await expect(mapHome).toHaveAttribute('href', /#\/map\?/);
  const mapHref = await mapHome.getAttribute('href') ?? '';
  expect(mapHref).toContain(`release_id=${releaseId}`);
  expect(mapHref).not.toContain('scenario=');
  expect(mapHref).not.toContain('f1a=');
  for (const taskLink of ['Contribute', 'About']) {
    const href = await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: taskLink, exact: true }).getAttribute('href') ?? '';
    const nestedMap = new URLSearchParams(href.split('?')[1] ?? '').get('map') ?? '';
    expect(nestedMap).toContain(`release_id=${releaseId}`);
    expect(nestedMap).not.toContain('scenario=');
    expect(nestedMap).not.toContain('f1a=');
  }
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
  await expect(mapLink).toHaveJSProperty('tabIndex', 0);
  await expect(mapLink).toHaveAttribute('href', /#\/map\?/);
  const databaseNavLink = page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database', exact: true });
  await expect(databaseNavLink).toHaveAttribute('href', /#\/database\?/);
  const destination = new URL(`http://test/${(await databaseNavLink.getAttribute('href') ?? '').slice(2)}`);
  expect(destination.pathname).toBe('/database');
  expect(destination.searchParams.get('lat')).toBe('45');
  expect(destination.searchParams.get('lon')).toBe('5');
});

test('public contribution contacts, merged About content, and code help are easy to find', async ({ page }) => {
  await page.goto('./#/contribute');
  await expect(page.getByRole('heading', { level: 1, name: 'Contribute to the project' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Contribute menu' })).toHaveCount(0);
  await expect(page.getByLabel('Contribution type')).toHaveCount(0);
  const tasks = page.getByRole('navigation', { name: 'Contribution tasks' });
  await expect(tasks).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Check status', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Community submissions', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Report a bug', exact: true })).toHaveAttribute('href', /#\/contribute\?type=bug/);
  await expect(page.locator('.contribute-page a[href="mailto:untileverycageproject@protonmail.com"]')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Contribute code on GitHub' })).toHaveAttribute('href', 'https://github.com/eliperez-dev/UntilEveryCage');
  const about = page.getByRole('link', { name: 'About', exact: true });
  await expect(about).toHaveText('About');
  await about.click();
  await expect(page.getByRole('heading', { name: 'About Until Every Cage is Empty' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Until Every Cage is Empty', level: 2 })).toBeVisible();
  await expect(page.getByRole('article', { name: 'About Until Every Cage', exact: true }).getByRole('link', { name: 'GitHub', exact: true })).toHaveAttribute('href', 'https://github.com/eliperez-dev/UntilEveryCage');
  const overview = await page.locator('.manifesto').innerText();
  await page.goto('./#/about/manifesto');
  const manifesto = await page.locator('.manifesto').innerText();
  expect(manifesto).toBe(overview);
  await expect(page.locator('.about-counter-slot')).toBeVisible();
  await expect(page.getByRole('main')).toHaveCount(1);
});
