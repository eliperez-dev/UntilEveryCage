import { expect, test, type Page } from '@playwright/test';

// Renderer tests use only synthetic public HTTP projections. The native map
// handle exists in development and is absent from production bundles.
const release = 'synthetic-hover-scope';
const id = '550e8400-e29b-41d4-a716-446655440000';
const point: [number, number] = [5, 45];
async function install(page: Page, precision = 'source_reported', filters = '', category = 'slaughter') {
  const state = { details: 0, delay: 0, status: 200, generation: 1, feeds: 0 };
  const meta = { profile: 'official', release_id: release, ruleset_version: 'synthetic-rules', release_created_at: '2026-01-01T00:00:00Z' };
  const row = { facility_id: id, canonical_name: 'Synthetic <img src=x onerror=alert(1)> facility', country_code: 'BE', city: 'Synthetic city', category, taxonomy_display_category: category, taxonomy_primary_categories: [category], publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved', reviewer_role: null, publication_warning: null, display_precision: precision, latitude: point[1], longitude: point[0], first_observed_at: null, last_observed_at: null, observation_count: 1, lifecycle_status: 'status_unknown', source_type: 'official', source_rights_status: 'cleared', provenance_source: null, release_id: release, release_ruleset_version: 'synthetic-rules', provenance_source_id: 'synthetic-source', provenance_source_name: 'Synthetic source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z' };
  await page.route('https://**/*', route => route.abort());
  await page.route('**/api/v2/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname;
    const identity = { profile: 'official', release_id: release, manifest_sha256: 'a'.repeat(64), suppression_generation: state.generation };
    if (path === '/api/v2/releases/manifest') return route.fulfill({ json: { api_version: 'v2', data: { ...identity, manifest: {} } } });
    if (path === '/api/v2/map/feed') { state.feeds++; return route.fulfill({ json: { api_version: 'v2', data: { type: 'FeatureCollection', features: [{ type: 'Feature', id, geometry: { type: 'Point', coordinates: point }, properties: { facility_id: id, source_id: 'synthetic-source', country_code: 'BE', category_key: category, category_keys: [category], precision, weight: 1 } }] }, meta: { ...identity, feature_count: 1, public_record_count: 1, unmapped_count: 0, release_label: 'Synthetic release', dataset_version: 'synthetic' } } }); }
    // Simulate a public pin outside the already loaded result page.
    if (path === '/api/v2/locations') return route.fulfill({ json: { api_version: 'v2', data: [{ ...row, facility_id: '550e8400-e29b-41d4-a716-446655440001', canonical_name: 'Another synthetic result' }], meta: { ...meta, coverage_note: 'Synthetic renderer checks.', next_cursor: null, total_count: 2 } } });
    if (path === `/api/v2/locations/${id}`) {
      state.details++; expect(url.searchParams.get('release_id')).toBe(release);
      if (state.delay) await new Promise(resolve => setTimeout(resolve, state.delay));
      return route.fulfill({ status: state.status, json: state.status === 200 ? { api_version: 'v2', data: row, meta } : {} }).catch(() => {});
    }
    if (path === '/api/v2/map/matches') return route.fulfill({ json: { api_version: 'v2', data: { facility_ids: [id] }, meta: { ...identity, total_count: 1, mapped_count: 1 } } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto(`./#/map?release_id=${release}&lat=45&lon=5&z=12${filters}`);
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getLayer('v1-source-pins') && map.isSourceLoaded('locations') && !map.isMoving();
  });
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.queryRenderedFeatures({ layers: ['v1-source-pins', 'approx-reference-pins', 'approx-reference-points'] }).length > 0;
  });
  return state;
}
async function hoverPin(page: Page, verticalOffset = 14) {
  const pixel = await page.evaluate(coordinates => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, p = map.project(coordinates), box = map.getCanvas().getBoundingClientRect();
    return { x: p.x + box.x, y: p.y + box.y };
  }, point);
  await page.mouse.move(pixel.x, pixel.y - verticalOffset);
  return { ...pixel, y: pixel.y - verticalOffset };
}
test('hover shows safe name/category without moving the camera, caches labels and leaves a cold approximate click intact', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const state = await install(page, 'approximate');
  const camera = await page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return [m.getCenter().toArray(), m.getZoom(), m.getPitch(), m.getBearing()]; });
  const pixel = await hoverPin(page);
  const tooltip = page.getByRole('tooltip');
  await expect(tooltip).toContainText('Synthetic <img src=x onerror=alert(1)> facility');
  await expect(tooltip).toContainText('Slaughter'); await expect(tooltip.locator('img, i')).toHaveCount(0);
  expect(await tooltip.evaluate(element => parseFloat(getComputedStyle(element).borderRadius))).toBeGreaterThanOrEqual(6);
  await page.screenshot({ path: testInfo.outputPath('public-pin-hover.png') });
  await page.getByRole('button', { name: 'Dark theme', exact: true }).click();
  await hoverPin(page); await expect(tooltip).toBeVisible();
  const contrast = await tooltip.evaluate(element => {
    const css = getComputedStyle(element);
    const luminance = (value: string) => { const channels = value.match(/[\d.]+/g)!.slice(0, 3).map(v => { const channel = Number(v) / 255; return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4; }); return .2126 * channels[0]! + .7152 * channels[1]! + .0722 * channels[2]!; };
    const bg = luminance(css.backgroundColor), fg = luminance(css.color);
    return { background: bg, ratio: (Math.max(bg, fg) + .05) / (Math.min(bg, fg) + .05) };
  });
  expect(contrast.background).toBeGreaterThan(.5); expect(contrast.ratio).toBeGreaterThan(4.5);
  await page.screenshot({ path: testInfo.outputPath('public-pin-hover-light.png') });
  expect(state.details).toBe(1); expect(new URL(page.url()).hash).not.toContain('selected=');
  expect(await page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return [m.getCenter().toArray(), m.getZoom(), m.getPitch(), m.getBearing()]; })).toEqual(camera);
  await page.mouse.move(10, 300); await expect(tooltip).toHaveCount(0);
  await hoverPin(page); await expect(tooltip).toBeVisible(); expect(state.details).toBe(1);
  await page.keyboard.press('Escape'); await expect(tooltip).toHaveCount(0);
  await page.mouse.click(pixel.x, pixel.y);
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${id}`);
  await expect(page.locator('.reading-sheet[aria-label="Record evidence"]')).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getSource('approximate-reference-area')?.getData().then((data: any) => data.features.length))).toBe(1);
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.panBy([-250, 0], { duration: 0 }));
  await page.mouse.move(10, 300);
  await hoverPin(page); await expect(tooltip).toBeVisible();
  await page.keyboard.press('Escape'); await expect(tooltip).toHaveCount(0);
  expect(new URL(page.url()).hash).toContain(`selected=${id}`);
});
test('leaving or moving the camera cancels slow hover; a restricted response never leaves a label', async ({ page }) => {
  const state = await install(page); state.delay = 500;
  await hoverPin(page); await expect.poll(() => state.details).toBe(1);
  await page.mouse.move(10, 300); await page.waitForTimeout(600); await expect(page.getByRole('tooltip')).toHaveCount(0);
  await hoverPin(page); await expect.poll(() => state.details).toBe(2);
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.panBy([40, 0], { duration: 0 }));
  await page.waitForTimeout(600); await expect(page.getByRole('tooltip')).toHaveCount(0);
  state.delay = 0; state.status = 404;
  await hoverPin(page); await expect.poll(() => state.details).toBe(3);
  await page.waitForTimeout(220); await expect(page.getByRole('tooltip')).toHaveCount(0);
});
test('area search outlines the exact snapshot through pan and basemap changes, then clears without reopening', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await install(page);
  await page.getByRole('button', { name: 'Search this area', exact: true }).click();
  const handle = page.getByRole('button', { name: 'Search map', exact: true });
  await expect(handle).toHaveAttribute('data-sheet-state', 'collapsed');
  const readArea = () => page.evaluate(async () => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('search-area')?.getData());
  await expect.poll(async () => (await readArea())?.features?.length).toBe(1);
  const before = await readArea();
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.panBy([70, 20], { duration: 0 }));
  expect(await readArea()).toEqual(before);
  await page.screenshot({ path: testInfo.outputPath('public-area-perimeter.png') });
  await page.getByRole('switch', { name: 'Map style: Street', exact: true }).click();
  await expect.poll(async () => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('search-area-outline', 'line-opacity'))).toBe(1);
  expect(await readArea()).toEqual(before); expect(state.feeds).toBe(1);
  await page.getByRole('button', { name: 'Clear area search', exact: true }).first().click();
  await expect.poll(async () => (await readArea())?.features?.length).toBe(0);
  await expect(handle).toHaveAttribute('data-sheet-state', 'collapsed');
});

test('hover stays readable near map edges and pin-size tuning changes art without changing the source', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const state = await install(page);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getLayoutProperty('v1-source-pins', 'icon-size'))).toBe(0.4);
  for (const offset of [[-690, 0], [1380, 0], [-690, 310]]) {
    await page.evaluate(delta => (window as any).__UEC_LOCAL_PREVIEW_MAP__.panBy(delta, { duration: 0 }), offset);
    await hoverPin(page); await expect(page.getByRole('tooltip')).toBeVisible();
    const box = await page.getByRole('tooltip').boundingBox(), canvas = await page.locator('.maplibregl-canvas').boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(canvas!.x); expect(box!.x + box!.width).toBeLessThanOrEqual(canvas!.x + canvas!.width);
    expect(box!.y).toBeGreaterThanOrEqual(canvas!.y); expect(box!.y + box!.height).toBeLessThanOrEqual(canvas!.y + canvas!.height);
  }
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  await page.getByText('Map tuning', { exact: true }).click();
  const slider = page.locator('#pin-scale'); await expect(slider).toHaveValue('0.8');
  await page.evaluate(() => {
    const source = (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('locations');
    (window as any).__syntheticSourceChanges = 0;
    for (const method of ['setData', 'setClusterOptions']) { const original = source[method].bind(source); source[method] = (...args: any[]) => { (window as any).__syntheticSourceChanges++; return original(...args); }; }
  });
  await slider.fill('1.2');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getLayoutProperty('v1-source-pins', 'icon-size'))).toBe(0.6);
  expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getLayoutProperty('v1-source-shadows', 'icon-size'))).toBe(1.2);
  expect(await page.evaluate(() => (window as any).__syntheticSourceChanges)).toBe(0); expect(state.feeds).toBe(1);
});

for (const precision of ['source_reported', 'approximate', 'city']) test(`ordinary display controls keep ${precision} dots selectable and sync with debug/reset`, async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const state = await install(page, precision, '&category=slaughter&country=BE');
  const camera = await page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return [m.getCenter().toArray(), m.getZoom(), m.getPitch(), m.getBearing()]; });
  const beforeHash = new URL(page.url()).hash;
  await page.evaluate(() => {
    const source = (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('locations');
    (window as any).__syntheticDisplayChanges = { data: 0, clusters: 0 };
    for (const [method, key] of [['setData', 'data'], ['setClusterOptions', 'clusters']]) { const original = source[method].bind(source); source[method] = (...args: any[]) => { (window as any).__syntheticDisplayChanges[key]++; return original(...args); }; }
  });
  const more = page.getByRole('button', { name: 'More tools', exact: true }); await more.click();
  await expect(page.locator('#map-clustering-choice')).toHaveValue('auto');
  await expect(page.getByRole('slider', { name: 'Icon size', exact: true })).toHaveValue('0.8');
  await page.getByRole('checkbox', { name: 'Use optimized pins', exact: true }).check();
  const dots = page.getByRole('slider', { name: 'Dot size', exact: true }); await expect(dots).toHaveValue('6.5'); await dots.fill('9');
  const layer = precision === 'source_reported' ? 'source-coordinate-points' : 'approx-reference-circles';
  await expect.poll(() => page.evaluate(target => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return [m.getLayoutProperty(target, 'visibility'), m.getPaintProperty(target, 'circle-radius')]; }, layer)).toEqual(['visible', 9]);
  expect(await page.evaluate(() => (window as any).__syntheticDisplayChanges)).toEqual({ data: 0, clusters: 0 });
  expect(await page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return [m.getCenter().toArray(), m.getZoom(), m.getPitch(), m.getBearing()]; })).toEqual(camera);
  expect(new URL(page.url()).hash).toBe(beforeHash); expect(state.feeds).toBe(1);
  await more.click(); const pixel = await hoverPin(page, 0); await expect(page.getByRole('tooltip')).toContainText('Slaughter');
  await page.mouse.click(pixel.x, pixel.y); await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${id}`);
  await more.click(); await page.locator('#map-clustering-choice').selectOption('off');
  await expect.poll(() => page.evaluate(() => (window as any).__syntheticDisplayChanges.clusters)).toBe(1);
  await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check(); await more.click();
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  const resetCamera = await page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return [m.getCenter().toArray(), m.getZoom(), m.getPitch(), m.getBearing()]; });
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click(); await page.getByText('Map tuning', { exact: true }).click();
  await expect(page.locator('#cluster-mode')).toHaveValue('off'); await expect(page.locator('#v1-pin-mode')).not.toBeChecked(); await expect(page.locator('#coordinate-radius')).toHaveValue('9');
  await page.getByRole('button', { name: 'Reset temporary settings', exact: true }).click();
  await expect(page.locator('#v1-pin-mode')).toBeChecked(); await expect(page.locator('#cluster-mode')).toHaveValue('auto'); await expect(page.locator('#pin-scale')).toHaveValue('0.8');
  await page.getByRole('button', { name: 'Close debug menu', exact: true }).click(); await more.click();
  await expect(page.getByRole('checkbox', { name: 'Use optimized pins', exact: true })).not.toBeChecked(); await expect(page.locator('#map-clustering-choice')).toHaveValue('auto');
  await expect(page.getByRole('slider', { name: 'Icon size', exact: true })).toHaveValue('0.8');
  expect(await page.evaluate(() => { const m = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return [m.getCenter().toArray(), m.getZoom(), m.getPitch(), m.getBearing()]; })).toEqual(resetCamera);
  expect(new URL(page.url()).hash).toContain('category=slaughter'); expect(new URL(page.url()).hash).toContain('country=BE'); expect(state.feeds).toBe(1);
});

test.describe('touch hover exclusion', () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  test('does not request or display hover details on touch pointers', async ({ page }) => {
    const state = await install(page); await hoverPin(page);
    await page.waitForTimeout(300); expect(state.details).toBe(0); await expect(page.getByRole('tooltip')).toHaveCount(0);
  });
});


for (const precision of ['source_reported','approximate','city']) test(`Processing keeps blue artwork in ${precision} pins and optimized dots`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width:1440, height:900 });
    await install(page, precision, '', 'processing_and_preparation');
    await expect.poll(() => page.evaluate(() => {
      const map=(window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return map.queryRenderedFeatures({ layers:['v1-source-pins','approx-reference-pins','approx-reference-points'] })
        .some((feature:any)=>map.style.getLayer(feature.layer.id).layout.get('icon-image').evaluate(feature).name==='v1-pin-blue');
    })).toBe(true);
    await hoverPin(page); await expect(page.getByRole('tooltip')).toContainText('Processing and preparation');
    await expect(page.getByRole('tooltip').locator('i,img')).toHaveCount(0);
    if (precision==='source_reported') await page.screenshot({path:testInfo.outputPath('processing-blue-hover.png')});
    await page.mouse.move(1400,800);
    await page.getByRole('button',{name:'More tools',exact:true}).click();
    await page.getByRole('checkbox',{name:'Use optimized pins',exact:true}).check();
    await page.getByRole('button',{name:'More tools',exact:true}).click();
    await expect.poll(()=>page.evaluate(()=>{
      const map=(window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return map.queryRenderedFeatures({layers:['source-coordinate-points','approx-reference-circles']})
        .some((feature:any)=>{
          const color=map.style.getLayer(feature.layer.id).paint.get('circle-color').evaluate(feature);
          return Math.abs(color.r-134/255)<.001 && Math.abs(color.g-167/255)<.001 && Math.abs(color.b-250/255)<.001;
        });
    })).toBe(true);
});
