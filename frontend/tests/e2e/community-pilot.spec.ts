import { expect, test, type Page } from '@playwright/test';

const id = '18c6ef3a-28cd-4c8e-a9bb-3951f45f210d';
const recordId = '27d7ef4b-39de-4d9f-bacc-4062f560321e';
const release = 'synthetic-community-release';
const claimWarning = 'Unreviewed community claim — not verified by Until Every Cage.';
const secret = 'synthetic-one-time-receipt-secret';

test.skip(process.env.VITE_COMMUNITY_PILOT !== 'true', 'Community pilot E2E requires explicit local pilot enablement.');

const claimDto = {
  submission_id: id, kind: 'facility', record_id: recordId, release_id: release,
  public_record_url: `/api/v2/locations/${recordId}?profile=community&release_id=${release}`,
  origin: 'community-submitted', factual_review_status: 'unreviewed', project_approval: 'not-approved', warning: claimWarning,
};
const rowDto = {
  submission_id: id, kind: 'facility', status: 'received', created_at: '2026-10-01T12:00:00Z',
  label: 'Synthetic facility claim', country_code: 'DK', locality: 'Sample locality', claimed_activity: 'Synthetic activity',
  source_url: 'https://example.test/synthetic-source', observed_on: '2026-09-20', description: 'Synthetic queue context',
  location_text: 'Broad synthetic area', claimed_precision: 'coarse', location_input_method: 'manual_pin',
  claimed_latitude: 55.7, claimed_longitude: 12.5, target_record_id: recordId, duplicate_record_id: null,
  contact_email: 'private-synthetic@example.test', receipt_secret_hash: 'synthetic-never-render',
};

async function mockCommunityApi(page: Page) {
  await page.route('https://tile.openstreetmap.org/**', route => route.abort());
  await page.route('https://server.arcgisonline.com/**', route => route.abort());
  await page.route('**/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (!path.startsWith('/api/')) { await route.fallback(); return; }
    if (path === '/api/community/submissions' && request.method() === 'POST') {
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ submission_id: id, receipt_secret: secret, status: 'received' }) });
    } else if (path === '/api/community/status' && request.method() === 'POST') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ submission_id: id, status: 'published', public_record_url: claimDto.public_record_url }) });
    } else if (path === '/api/private/community/submissions' && request.method() === 'GET') {
      const status = url.searchParams.get('status');
      const statusForResponse = status === 'screened' ? 'screened' : 'received';
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ pending_count: 1, submissions: [{ ...rowDto, status: statusForResponse }] }) });
    } else if (path.endsWith('/disposition') && request.method() === 'POST') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'screened' }) });
    } else if (path === '/api/v2/releases/manifest') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ api_version: 'v2', data: { profile: 'community', release_id: release } }) });
    } else if (path === '/api/community/claims' && request.method() === 'GET') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ claims: [claimDto], claim_count: 1, warning: claimWarning }) });
    } else if (path === `/api/community/claims/${id}` && request.method() === 'GET') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(claimDto) });
    } else {
      await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
    }
  });
}

test.beforeEach(async ({ page }) => mockCommunityApi(page));

test('status route can transition through the Contribute hub and the pin can be added and cleared', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.goto('#/contribution-status');
  await expect(page.getByRole('heading', { name: 'Check contribution status' })).toBeVisible();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Contribute' }).click();
  await expect(page.getByRole('heading', { name: 'Add a facility' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Contribution tasks' }).getByRole('link', { name: 'Facility', exact: true })).toHaveAttribute('aria-current', 'page');
  const canvas = page.locator('.pin-map canvas');
  await expect(canvas).toBeVisible();
  await expect(page.locator('.pin-map .maplibregl-ctrl-zoom-in')).toBeVisible();
  await expect.poll(() => page.locator('.pin-map .maplibregl-ctrl-attrib').count()).toBeGreaterThan(0);
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await expect(page.getByLabel('Latitude')).not.toHaveValue('');
  await expect(page.getByLabel('Longitude')).not.toHaveValue('');
  await expect(page.locator('.contribution-pin')).toBeVisible();
  await page.getByRole('button', { name: 'Clear selected point' }).click();
  await expect(page.getByLabel('Latitude')).toHaveValue('');
  await expect(page.getByLabel('Longitude')).toHaveValue('');
  await page.getByLabel('Latitude').fill('55.7');
  await page.getByLabel('Longitude').fill('12.5');
  await expect(page.getByLabel('Latitude')).toHaveValue('55.7');
  await expect(page.getByLabel('Longitude')).toHaveValue('12.5');
  await expect(page.locator('.contribution-pin')).toBeVisible();
  await page.getByLabel('Latitude').fill('91');
  await expect(page.getByLabel('Latitude')).toHaveValue('91');
  await page.getByLabel('Latitude').fill('55.7');
  await page.getByRole('navigation', { name: 'Contribution tasks' }).getByRole('link', { name: 'Evidence', exact: true }).click();
  await expect(page.locator('.pin-map')).toHaveCount(0);
  await page.getByRole('navigation', { name: 'Contribution tasks' }).getByRole('link', { name: 'Facility', exact: true }).click();
  await expect(page.locator('.pin-map')).toBeVisible();
  await expect(page.getByLabel('Latitude')).toHaveValue('');
  expect(pageErrors).toEqual([]);
});

test('form remains usable with coordinate fallback when map construction fails', async ({ page }) => {
  await page.addInitScript(() => {
    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type: string, ...args: unknown[]) {
      if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') return null;
      return originalGetContext.call(this, type, ...(args as []));
    } as typeof HTMLCanvasElement.prototype.getContext;
  });
  let submitted: Record<string, unknown> | undefined;
  await page.route('**/api/community/submissions', async route => {
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ submission_id: id, receipt_secret: secret, status: 'received' }) });
  });
  await page.goto('#/contribute/facility');
  await expect(page.getByText('The map could not be opened. You can enter coordinates below instead.')).toBeVisible();
  await page.getByLabel('Latitude').fill('55.7');
  await page.getByLabel('Longitude').fill('12.5');
  await page.getByLabel('Facility name').fill('Synthetic fallback facility');
  await page.getByLabel('Country (optional)').selectOption('DK');
  await page.getByLabel('Source link (optional)').fill('https://example.test/fallback-source');
  await page.getByLabel(/I have permission to share/).check();
  await page.getByRole('button', { name: 'Send for review' }).click();
  await expect(page.getByRole('heading', { name: 'Contribution received' })).toBeVisible();
  expect(submitted).toMatchObject({ claimed_latitude: 55.7, claimed_longitude: 12.5, location_input_method: 'text' });
});

test('a valid submission displays its receipt once in memory without putting it in the URL', async ({ page }) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route('**/api/community/submissions', async route => {
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ submission_id: id, receipt_secret: secret, status: 'received' }) });
  });
  await page.goto('#/contribute/facility');
  await page.getByLabel('Facility name').fill('Synthetic facility claim');
  await page.getByLabel('Country (optional)').selectOption('DK');
  await page.getByLabel('Source link (optional)').fill('https://example.test/synthetic-source');
  await page.getByLabel(/I have permission to share/).check();
  await page.getByRole('button', { name: 'Send for review' }).click();
  await expect(page.getByRole('heading', { name: 'Contribution received' })).toBeVisible();
  await expect(page.getByLabel('Private receipt', { exact: true })).toHaveValue(secret);
  expect(submitted).toMatchObject({ kind: 'facility', consent: true, claimed_precision: 'unknown' });
  expect(submitted).not.toHaveProperty('contact_email');
  expect(page.url()).not.toContain(secret);
  await page.getByRole('link', { name: 'Check contribution status', exact: true }).click();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Contribute' }).click();
  await expect(page.getByRole('heading', { name: 'Add a facility' })).toBeVisible();
  await expect(page.getByLabel('Private receipt', { exact: true })).toHaveCount(0);
});

test('the operator queue shows structured private context but never contact or receipt fields', async ({ page }) => {
  await page.goto('#/contribution-review');
  await expect(page.getByText(/Private intake warning/)).toBeVisible();
  await page.getByLabel('Local operator token').fill('synthetic-operator-token');
  await page.getByRole('button', { name: 'Open restricted queue' }).click();
  for (const value of ['Synthetic facility claim', 'Denmark', 'Sample locality', 'Synthetic activity', '2026-09-20', 'Broad synthetic area', 'coarse', 'map pin', 'Synthetic queue context']) {
    await expect(page.getByText(value, { exact: false })).toBeVisible();
  }
  await expect(page.getByText('private-synthetic@example.test')).toHaveCount(0);
  await expect(page.getByText('synthetic-never-render')).toHaveCount(0);
  await expect(page.getByText(/Link to an existing community release record/)).toHaveCount(0);
  await page.getByRole('button', { name: 'Privacy screen only' }).click();
  await page.getByLabel('Status filter').selectOption('screened');
  await page.getByRole('button', { name: 'Refresh queue' }).click();
  await expect(page.getByText(/Link to an existing community release record/)).toBeVisible();
  await expect(page.getByText(/does not verify facts or approve a curated release/)).toBeVisible();
});

test('community claims are opt-in, scoped to the current profile, and prominently warned', async ({ page }) => {
  await page.goto('#/community');
  await expect(page.getByText(claimWarning)).toBeVisible();
  await page.getByRole('button', { name: 'Open community profile' }).click();
  await expect(page.getByText('1 community claims · separate profile count')).toBeVisible();
  await page.locator('.claim-row').click();
  await expect(page.getByRole('heading', { name: 'Community claim' })).toBeVisible();
  await expect(page.getByText(claimWarning)).toBeVisible();
  await page.getByRole('button', { name: 'Load this claim' }).click();
  await expect(page.getByRole('link', { name: 'View released record data (JSON)' })).toBeVisible();
});

test('a facility can be submitted with only a name and consent', async ({ page }) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route('**/api/community/submissions', async route => {
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ submission_id: id, receipt_secret: secret, status: 'received' }) });
  });
  await page.goto('#/contribute/facility');
  await page.getByLabel('Facility name').fill('Synthetic facility without location metadata');
  await page.getByLabel(/I have permission to share/).check();
  await page.getByRole('button', { name: 'Send for review' }).click();
  await expect(page.getByRole('heading', { name: 'Contribution received' })).toBeVisible();
  expect(submitted).toMatchObject({ kind: 'facility', label: 'Synthetic facility without location metadata', consent: true });
  expect(submitted).not.toHaveProperty('country_code');
  expect(submitted).not.toHaveProperty('source_url');
  expect(submitted).not.toHaveProperty('claimed_latitude');
});

test('six contribution task links switch in place with prefilled records and cleared draft state', async ({ page }) => {
  let communityWrites = 0;
  await page.route('**/api/community/submissions', async route => {
    communityWrites += 1;
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ submission_id: id, receipt_secret: secret, status: 'received' }) });
  });
  await page.goto(`#/contribute/evidence?target=${recordId}&map=%23%2Fmap%3Ff1a%3Dfield`);
  const tasks = page.getByRole('navigation', { name: 'Contribution tasks' });
  const switchTask = async (name: string) => tasks.getByRole('link', { name, exact: true }).click();
  await expect(tasks.getByRole('link', { name: 'Evidence', exact: true })).toHaveAttribute('aria-current', 'page');
  await expect(page.getByLabel('Record link or ID', { exact: true })).toHaveValue(recordId);
  await page.getByLabel('What did you find?').fill('Synthetic draft that must be cleared');
  await switchTask('Correction');
  await expect(page.getByLabel('What should be corrected?')).toHaveValue('');
  await expect(page.getByLabel('Record ID', { exact: true })).toHaveValue(recordId);
  await switchTask('Duplicate');
  await expect(page.getByLabel('Possible duplicate record ID')).toBeVisible();
  await expect(page.locator('.pin-map')).toHaveCount(0);
  await switchTask('Privacy/removal');
  await expect(page.getByLabel('What should we review?')).toBeVisible();
  await expect(page.getByLabel('Possible duplicate record ID')).toHaveCount(0);
  await switchTask('Bug report');
  await page.getByLabel('What happened?').fill('Synthetic bug draft');
  await page.getByLabel('Steps to reproduce').fill('Switch a synthetic form.');
  await page.getByRole('button', { name: 'Prepare email' }).click();
  await expect(page.getByRole('link', { name: 'Open email draft' })).toBeVisible();
  expect(communityWrites).toBe(0);
  await switchTask('Facility');
  await expect(page.getByLabel('Facility name')).toHaveValue('');
  await page.getByLabel('Facility name').fill('Synthetic selector submission');
  await page.getByLabel(/I have permission to share/).check();
  await page.getByRole('button', { name: 'Send for review' }).click();
  await expect(page.getByLabel('Private receipt', { exact: true })).toHaveValue(secret);
  await switchTask('Bug report');
  await expect(page.getByLabel('Private receipt', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('What happened?')).toHaveValue('');
  await expect(page.getByRole('link', { name: 'Open email draft' })).toHaveCount(0);
  expect(communityWrites).toBe(1);
  expect(page.url()).not.toContain(secret);
  const params = new URLSearchParams(new URL(page.url()).hash.split('?')[1]);
  expect(params.get('map')).toBe('#/map?f1a=field');
  expect(params.get('target')).toBe(recordId);
});

test('the text-only About menu supports keyboard, dismissal, and direct destination links', async ({ page }) => {
  await page.goto('#/contribute');
  const about = page.getByRole('button', { name: 'About', exact: true });
  await about.focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.locator('#shared-about-nav').getByRole('link', { name: 'Overview' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(about).toBeFocused();
  await expect(about).toHaveAttribute('aria-expanded', 'false');
  await about.click();
  await about.focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.locator('#shared-about-nav').getByRole('link', { name: 'Overview' })).toBeFocused();
  await page.getByRole('main').click({ position: { x: 10, y: 220 } });
  await expect(about).toHaveAttribute('aria-expanded', 'false');
  await page.getByRole('navigation', { name: 'Contribution tasks' }).getByRole('link', { name: 'Privacy/removal', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Privacy or removal', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Contribute menu' })).toHaveCount(0);
});

test('compact pages and dropdowns work on a narrow touch screen without overflow', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 360, height: 800 }, hasTouch: true, isMobile: true });
  const page = await context.newPage();
  await mockCommunityApi(page);
  await page.goto(`${process.env.UEC_REAL_PREVIEW_URL ?? 'http://127.0.0.1:4173/v2-preview/'}#/contribute`);
  for (const task of ['Facility', 'Evidence', 'Correction', 'Duplicate', 'Privacy/removal', 'Bug report']) {
    await page.getByRole('navigation', { name: 'Contribution tasks' }).getByRole('link', { name: task, exact: true }).tap();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  await page.getByRole('button', { name: 'About', exact: true }).tap();
  const sources = page.locator('#shared-about-nav').getByRole('link', { name: 'Sources & methodology' });
  const box = await sources.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(360);
  await sources.tap();
  await expect(page.getByRole('heading', { name: 'Sources & Methodology' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await context.close();
});

test('published status records past publication without promising a currently available claim', async ({ page }) => {
  let showPublicLink = false;
  await page.route('**/api/community/status', route => route.fulfill({contentType:'application/json',body:JSON.stringify({submission_id:id,status:'published',...(showPublicLink ? {public_record_url:claimDto.public_record_url} : {})})}));
  await page.goto('#/contribution-status');
  await page.getByLabel('Submission ID',{exact:true}).fill(id);
  await page.getByLabel('Private receipt',{exact:true}).fill(secret);
  await page.getByRole('button',{name:'Check status',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Published to community submissions',exact:true})).toBeVisible();
  await expect(page.getByText('Your contribution was published as an unreviewed community claim, separate from the curated release.',{exact:true})).toBeVisible();
  await expect(page.getByText('No public link is currently available.',{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Open the claim details',exact:true})).toHaveCount(0);
  showPublicLink = true;
  await page.getByRole('button',{name:'Check status',exact:true}).click();
  await expect(page.getByRole('link',{name:'Open the claim details',exact:true})).toHaveAttribute('href',`#/community/claim?id=${id}&release_id=${release}`);
  await expect(page.getByText('No public link is currently available.',{exact:true})).toHaveCount(0);
});
