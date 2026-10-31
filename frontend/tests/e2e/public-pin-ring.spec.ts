import { expect, test, type Page } from '@playwright/test';

const point: [number, number] = [5, 45];
const id = (i: number) => `550e8400-e29b-41d4-a716-${i.toString(16).padStart(12, '0')}`;
const categories = ['slaughter', 'processing_and_preparation', 'research_and_animal_use'];
async function install(page: Page, count: number, labelDelay = 0) {
  const release = `synthetic-overlap-${count}`;
  page.on('pageerror', error => console.log('Synthetic ring page error:', error.message));
  const state = { feeds: 0, privateRequests: 0, detailRequests: 0, onlyFirst: false };
  const meta = { profile: 'official', release_id: release, ruleset_version: 'synthetic-rules', release_created_at: '2026-01-01T00:00:00Z' };
  const rows = Array.from({ length: count }, (_, i) => ({ facility_id: id(i + 1), canonical_name: `Synthetic facility ${i + 1}`, country_code: 'BE', city: 'Synthetic city', category: categories[i % 3], taxonomy_display_category: categories[i % 3], taxonomy_primary_categories: [categories[i % 3]], publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved', reviewer_role: null, publication_warning: null, display_precision: i % 2 ? 'approximate' : 'source_reported', latitude: point[1], longitude: point[0], first_observed_at: null, last_observed_at: null, observation_count: 1, lifecycle_status: 'status_unknown', source_type: 'official', source_rights_status: 'cleared', provenance_source: null, release_id: release, release_ruleset_version: 'synthetic-rules', provenance_source_id: 'synthetic-source', provenance_source_name: 'Synthetic source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z' }));
  await page.route('https://**/*', route => route.abort());
  await page.route('**/api/private/**', route => { state.privateRequests++; return route.fulfill({ status: 404, json: {} }); });
  await page.route('**/api/v2/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname;
    const identity = { profile: 'official', release_id: release, manifest_sha256: 'b'.repeat(64), suppression_generation: 1 };
    if (path.includes('/private/') || path.includes('/reference')) { state.privateRequests++; return route.fulfill({ status: 404, json: {} }); }
    if (path === '/api/v2/releases/manifest') return route.fulfill({ json: { api_version: 'v2', data: { ...identity, manifest: {} } } });
    if (path === '/api/v2/map/feed') {
      state.feeds++;
      return route.fulfill({ json: { api_version: 'v2', data: { type: 'FeatureCollection', features: rows.map(row => ({ type: 'Feature', id: row.facility_id, geometry: { type: 'Point', coordinates: point }, properties: { facility_id: row.facility_id, source_id: 'synthetic-source', country_code: 'BE', category_key: row.category, category_keys: [row.category], precision: row.display_precision, weight: 1 } })) }, meta: { ...identity, feature_count: count, public_record_count: count, unmapped_count: 0, release_label: 'Synthetic release', dataset_version: 'synthetic' } } });
    }
    if (path === '/api/v2/locations') return route.fulfill({ json: { api_version: 'v2', data: state.onlyFirst ? rows.slice(0, 1) : rows, meta: { ...meta, coverage_note: 'Synthetic renderer checks.', next_cursor: null, total_count: state.onlyFirst ? 1 : count } } });
    const detail = rows.find(row => path === `/api/v2/locations/${row.facility_id}`);
    if (detail) {
      state.detailRequests++;
      if (labelDelay) await new Promise(resolve => setTimeout(resolve, labelDelay));
      return route.fulfill({ json: { api_version: 'v2', data: detail, meta } });
    }
    if (path === '/api/v2/map/matches') { const ids = (state.onlyFirst ? rows.slice(0, 1) : rows).map(row => row.facility_id); return route.fulfill({ json: { api_version: 'v2', data: { facility_ids: ids }, meta: { ...identity, total_count: ids.length, mapped_count: ids.length } } }); }
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto(`./#/map?release_id=${release}&lat=45&lon=5&z=12`);
  await page.waitForFunction(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return m?.getLayer('v1-source-pins') && m.isSourceLoaded('locations') && !m.isMoving(); }, undefined, { timeout: 15000 }).catch(async error => { console.log('Synthetic map startup:', await page.locator('body').innerText(), await page.evaluate(() => ({ map: !!(window as any).__UEC_LOCAL_PREVIEW_MAP__, href: location.href }))); throw error; });
  await expect.poll(() => page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return m.queryRenderedFeatures({ layers: ['v1-source-pins', 'approx-reference-pins'] }).length; })).toBeGreaterThan(0);
  return state;
}
async function clickPoint(page: Page) {
  const p = await page.evaluate(coordinates => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__, p = m.project(coordinates), r = m.getCanvas().getBoundingClientRect(); return { x: r.x + p.x, y: r.y + p.y - 13 }; }, point);
  await page.mouse.click(p.x, p.y);
}
async function camera(page: Page) { return page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return [m.getCenter().toArray(), m.getZoom(), m.getPitch(), m.getBearing()]; }); }

for (const mobile of [false, true]) test(`ring opens exact public members and preserves camera on ${mobile ? 'phone' : 'desktop'}`, async ({ page }, info) => {
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 });
  const state = await install(page, 8), before = await camera(page);
  await clickPoint(page);
  const ring = page.locator('.public-pin-ring'); await expect(ring).toBeVisible();
  await expect(page.locator('.ring-heading')).toContainText('8');
  expect(new URL(page.url()).hash).not.toContain('selected=');
  expect(await camera(page)).toEqual(before);
  await expect.poll(() => page.locator('.ring-member img').evaluateAll(images => images.every(image => (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0))).toBe(true);
  await expect(page.locator('.ring-guides circle')).toHaveCount(1);
  // The pin tips, guide and connector endpoints share one display coordinate.
  await expect.poll(() => page.evaluate(() => {
    const ring = document.querySelector('.public-pin-ring')!.getBoundingClientRect();
    const pins = [...document.querySelectorAll<HTMLImageElement>('.ring-member img')];
    const lines = [...document.querySelectorAll<SVGLineElement>('.ring-connections line')];
    return Math.max(...pins.map((pin, i) => {
      const art = pin.getBoundingClientRect(), line = lines[i]!;
      return Math.max(Math.abs(art.x + art.width / 2 - ring.x - line.x2.baseVal.value), Math.abs(art.bottom - ring.y - line.y2.baseVal.value));
    }));
  })).toBeLessThan(1);
  await page.screenshot({ path: info.outputPath(mobile ? 'ring-phone.png' : 'ring-desktop.png') });
  // Stable ordering makes the second member the approximate record, even when a different pin is painted on top.
  await page.locator('.ring-member').nth(1).click();
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${id(2)}`);
  await expect(page.locator('.reading-sheet[aria-label="Record evidence"]')).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('approximate-reference-area')?.getData().then((d: any) => d.features.length))).toBe(1);
  expect(await camera(page)).toEqual(before); expect(state.feeds).toBe(1); expect(state.privateRequests).toBe(0);
  await page.screenshot({ path: info.outputPath(mobile ? 'ring-detail-phone.png' : 'ring-detail-desktop.png') });
});

for (const count of [214, 614]) test(`large overlap lists reach all ${count} public records without rebuilding the native source`, async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const state = await install(page, count); await clickPoint(page);
  await expect(page.locator('.public-pin-ring')).toBeVisible();
  await page.evaluate(() => { const s = (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('locations'), original = s.setData.bind(s); (window as any).__ringSourceWrites = 0; s.setData = (...args: any[]) => { (window as any).__ringSourceWrites++; return original(...args); }; });
  const before = await camera(page);
  await expect(page.locator('.ring-heading')).toContainText(String(count));
  await expect(page.locator('.ring-pager')).toHaveCount(0);
  await expect(page.locator('.ring-member')).toHaveCount(count);
  await expect(page.locator('.ring-zoom')).toHaveCount(0);
  await page.locator('.ring-member').first().press('End');
  const last = page.locator(`.ring-member[data-record-id="${id(count)}"]`);
  await expect(last).toBeFocused(); await expect(last).toBeVisible();
  await last.press('ArrowLeft'); await expect(page.locator(`.ring-member[data-record-id="${id(count - 1)}"]`)).toBeFocused();
  await page.keyboard.press('Home'); await expect(page.locator(`.ring-member[data-record-id="${id(1)}"]`)).toBeFocused();
  expect(await camera(page)).toEqual(before);
  await page.screenshot({ path: info.outputPath(`concentric-${count}.png`) });
  await page.keyboard.press('End'); await last.click();
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${id(count)}`);
  expect(await page.evaluate(() => (window as any).__ringSourceWrites)).toBe(0);
  expect(state.feeds).toBe(1); expect(state.privateRequests).toBe(0);
});

test('single records stay direct', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await install(page, 1); await clickPoint(page);
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${id(1)}`);
  await expect(page.locator('.public-pin-ring')).toHaveCount(0);
});

test('optimized dots and coincident native clusters open the ring', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await install(page, 18);
  const more = page.getByRole('button', { name: 'More tools', exact: true });
  await more.click(); await page.getByRole('checkbox', { name: 'Use optimized pins', exact: true }).check(); await page.locator('#map-clustering-choice').selectOption('off'); await more.click();
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  await expect.poll(() => page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return m.getLayoutProperty('source-coordinate-points', 'visibility') === 'visible' && m.isSourceLoaded('locations'); })).toBe(true);
  const p = await page.evaluate(coordinates => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__, p = m.project(coordinates), r = m.getCanvas().getBoundingClientRect(); return { x: r.x + p.x, y: r.y + p.y }; }, point);
  await page.mouse.click(p.x, p.y); await expect(page.locator('.ring-dot').first()).toBeVisible();
  expect(await page.locator('.ring-dot').count()).toBeGreaterThan(12);
  await page.keyboard.press('Escape'); await expect(page.locator('.public-pin-ring')).toHaveCount(0);
  await more.click(); await page.locator('#map-clustering-choice').selectOption('on'); await more.click();
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ zoom: 4 }));
  await expect.poll(() => page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return m.queryRenderedFeatures({ layers: ['clusters'] }).length; })).toBeGreaterThan(0);
  const before = await camera(page); const c = await page.evaluate(coordinates => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__, p = m.project(coordinates), r = m.getCanvas().getBoundingClientRect(); return { x: r.x + p.x, y: r.y + p.y }; }, point);
  await page.mouse.click(c.x, c.y); await expect(page.locator('.public-pin-ring')).toBeVisible(); expect(await camera(page)).toEqual(before);
});

test('new query membership clears the old ring and counts', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const state = await install(page, 81); await clickPoint(page);
  await expect(page.locator('.public-pin-ring')).toBeVisible();
  state.onlyFirst = true;
  await page.getByRole('button', { name: 'Search map', exact: true }).click();
  await page.locator('#field-search').fill('only first');
  await expect(page.locator('.public-pin-ring')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('locations').getData().then((d: any) => d.features.length))).toBe(1);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('public-pin-stacks').getData().then((d: any) => d.features.length))).toBe(0);
  await clickPoint(page);
  await expect(page.locator('.public-pin-ring')).toHaveCount(0);
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${id(1)}`);
  expect(state.privateRequests).toBe(0);
});

test('short phones retain an explicit way back to the ring after selection', async ({ page }, info) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await install(page, 8); await clickPoint(page);
  await expect(page.locator('.ring-member').first()).toBeVisible();
  await page.locator('.ring-member').nth(1).click();
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${id(2)}`);
  const before = await camera(page);
  const reopen = page.getByRole('button', { name: '8 Open overlapping records', exact: true });
  await expect(reopen).toBeVisible();
  await page.screenshot({ path: info.outputPath('ring-short-phone-detail.png') });
  await reopen.click();
  await expect(page.locator('.ring-member').first()).toBeVisible();
  expect(await camera(page)).toEqual(before);
  expect(new URL(page.url()).hash).toContain(`selected=${id(2)}`);
  await page.screenshot({ path: info.outputPath('ring-short-phone-reopened.png') });
});

test('compact rings keep the same position through keyboard navigation and selection', async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await install(page, 36); await clickPoint(page);
  await expect(page.locator('.ring-member')).toHaveCount(36);
  await expect(page.locator('.ring-guides circle')).toHaveCount(3);
  await expect(page.locator('.ring-zoom')).toHaveCount(0);
  await expect(page.locator('.public-pin-ring')).not.toHaveClass(/opening/);
  const before = await camera(page);
  const positions = () => page.locator('.ring-member').evaluateAll(elements => elements.map(el => [el.getAttribute('data-record-id'), (el as HTMLElement).style.left, (el as HTMLElement).style.top]));
  const original = await positions();
  const guide = await page.locator('.ring-guides circle').first().evaluate(el => [el.getAttribute('cx'), el.getAttribute('cy')]);
  await page.locator('.ring-member').first().press('End');
  await expect(page.locator(`.ring-member[data-record-id="${id(36)}"]`)).toBeFocused();
  expect(await positions()).toEqual(original);
  const bounds = await page.locator('.ring-viewport').boundingBox();
  expect(bounds!.width).toBeLessThan(450); expect(bounds!.height).toBeLessThan(450);
  await page.locator('.ring-member').nth(1).click();
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${id(2)}`);
  expect(await positions()).toEqual(original);
  expect(await page.locator('.ring-guides circle').first().evaluate(el => [el.getAttribute('cx'), el.getAttribute('cy')])).toEqual(guide);
  expect(await camera(page)).toEqual(before);
  await page.screenshot({ path: info.outputPath('compact-fixed-rings.png') });
});

test('large groups scroll on a German phone without ring zoom controls', async ({ page }, info) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await install(page, 614);
  await page.locator('.language-action').click();
  await page.getByRole('button', { name: 'Deutsch', exact: true }).click();
  await clickPoint(page);
  const before = await camera(page);
  await expect(page.locator('.ring-member')).toHaveCount(614);
  await expect(page.locator('.ring-zoom')).toHaveCount(0);
  await page.locator('.ring-member').first().press('End');
  const last = page.locator(`.ring-member[data-record-id="${id(614)}"]`);
  await expect(last).toBeFocused(); await expect(last).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await camera(page)).toEqual(before);
  await page.screenshot({ path: info.outputPath('compact-phone-german.png') });
  await last.click();
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${id(614)}`);
});

test('ring labels warm before hover without flashing numbered placeholders', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const state = await install(page, 8, 300);
  await page.evaluate(() => {
    (window as any).__numberedRingLabel = false;
    new MutationObserver(() => {
      if (/^Record\s+\d+$/.test(document.querySelector('.ring-tooltip strong')?.textContent ?? '')) (window as any).__numberedRingLabel = true;
    }).observe(document.body, { subtree: true, childList: true, characterData: true });
  });
  await clickPoint(page);
  const second = page.locator(`.ring-member[data-record-id="${id(2)}"]`);
  await second.hover();
  await expect(page.locator('.ring-tooltip')).toContainText('Synthetic facility 2');
  await expect.poll(() => page.locator(`.ring-member[data-record-id="${id(8)}"]`).getAttribute('aria-label')).toContain('Synthetic facility 8');
  expect(state.detailRequests).toBeLessThanOrEqual(8);
  await page.locator(`.ring-member[data-record-id="${id(8)}"]`).hover();
  await expect(page.locator('.ring-tooltip')).toContainText('Synthetic facility 8');
  expect(await page.evaluate(() => (window as any).__numberedRingLabel)).toBe(false);
});
