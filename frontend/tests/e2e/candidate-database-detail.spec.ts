import { expect, test } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

test('configured candidate database opens source-native detail facts', async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto('/v2-preview/#/database?f1a=field&source=us.fsis');
  const table = page.getByRole('table', { name: 'Browse records' });
  await expect(table).toBeVisible({ timeout: 60_000 });
  const fsisRecordId = await page.evaluate(async () => {
    const listResponse = await fetch('/api/dev/preview/test-release/locations?profile=official&limit=1000&source_id=us.fsis', { cache: 'no-store' });
    if (!listResponse.ok) throw new Error('FSIS candidate list was unavailable.');
    const list = await listResponse.json();
    for (const row of list.data.slice(0, 100)) {
      const detailResponse = await fetch(`/api/dev/preview/test-release/locations/${encodeURIComponent(row.facility_id)}`, { cache: 'no-store' });
      if (!detailResponse.ok) continue;
      const detail = await detailResponse.json();
      const species = detail.data?.species_slaughtered;
      const affirmativeSpecies = species && typeof species === 'object'
        ? Object.values(species).filter(value => value === true || (typeof value === 'string' && value.trim().length > 0)).length
        : 0;
      if (affirmativeSpecies >= 2 && Array.isArray(detail.data?.derived_source_volume_ranges) && detail.data.derived_source_volume_ranges.length > 0) return row.facility_id;
    }
    throw new Error('No FSIS detail with multiple species and a derived source range was returned.');
  });
  await page.goto(`/v2-preview/#/records/${fsisRecordId}?f1a=field`);

  const detail = page.locator('.detail');
  await expect(detail.getByRole('heading', { name: 'Source facts' })).toBeVisible({ timeout: 30_000 });
  await expect(detail.getByText('Location precision', { exact: true })).toBeVisible();
  await expect(detail.getByText('Species slaughtered', { exact: true })).toBeVisible();
  await expect.poll(() => detail.locator('dt:has-text("Species slaughtered") + dd li').count(), { timeout: 30_000 }).toBeGreaterThan(1);
  await expect(detail.getByText('Processing activities', { exact: true })).toBeVisible();
  await expect(detail.getByText('Source volume categories', { exact: true })).toBeVisible();
  await expect(detail.getByText('Estimated product volume (pounds/month)', { exact: true })).toBeVisible();
  await expect(detail).not.toContainText('API unavailable');
  await expect(detail).not.toContainText('Name not shown, privacy review pending');
});

test('candidate map exposes projection-cache invalidation through Tools', async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto('/v2-preview/#/map?f1a=field&source=us.fsis');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return Boolean(map?.isStyleLoaded() && map.isSourceLoaded('locations'));
  }, undefined, { timeout: 60_000 });
  await page.getByRole('button', { name: 'Tools' }).click();
  await page.getByLabel('Enable debug menu').check();
  await page.getByRole('button', { name: 'Debug menu' }).click();
  const debug = page.getByRole('complementary', { name: 'Debug menu' });
  await expect(debug.getByRole('button', { name: 'Clear map projection cache' })).toBeVisible({ timeout: 60_000 });
  await debug.getByRole('button', { name: 'Clear map projection cache' }).click();
  await expect(debug.locator('small[role="status"]')).toContainText(/cache/i);
});

test('candidate map marker opens the configured source-backed detail', async ({ page }) => {
  test.setTimeout(90_000);
  const feedTiming: { requested?: number; response?: number; finished?: number; status?: number } = {};
  page.on('request', request => { if (new URL(request.url()).pathname.endsWith('/api/dev/preview/test-release/map/feed')) feedTiming.requested = Date.now(); });
  page.on('response', response => { if (new URL(response.url()).pathname.endsWith('/api/dev/preview/test-release/map/feed')) { feedTiming.response = Date.now(); feedTiming.status = response.status(); } });
  page.on('requestfinished', request => { if (new URL(request.url()).pathname.endsWith('/api/dev/preview/test-release/map/feed')) feedTiming.finished = Date.now(); });
  await page.goto('/v2-preview/#/map?f1a=field&source=us.fsis');
  try {
    await page.waitForFunction(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return Boolean(map?.isStyleLoaded() && map.getSource('locations') && map.querySourceFeatures('locations').some((feature: any) => feature.properties?.kind === 'source-coordinate'));
    }, undefined, { timeout: 60_000 });
  } catch {
    const state = await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return {
        styleLoaded: Boolean(map?.isStyleLoaded()),
        sourcePresent: Boolean(map?.getSource('locations')),
        sourceFeatures: map?.getSource('locations') ? map.querySourceFeatures('locations').length : 0,
        rendered: map?.queryRenderedFeatures({ layers: ['source-coordinate-points'] }).length ?? 0,
        status: document.querySelector('[role="status"]')?.textContent?.trim().slice(0, 80) ?? '',
      };
    });
    throw new Error(`candidate map marker probe stalled: ${JSON.stringify({ feedTiming, state })}`);
  }
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const sourceFeature = map.querySourceFeatures('locations').find((feature: any) => feature.properties?.kind === 'source-coordinate');
    map.jumpTo({ center: sourceFeature.geometry.coordinates, zoom: 14 });
  });
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.queryRenderedFeatures({ layers: ['source-coordinate-points'] }).length > 0;
  }, undefined, { timeout: 30_000 });
  const point = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const rendered = map.queryRenderedFeatures({ layers: ['source-coordinate-points'] })[0];
    const projected = map.project(rendered.geometry.coordinates);
    const bounds = map.getContainer().getBoundingClientRect();
    return { x: bounds.left + projected.x, y: bounds.top + projected.y };
  });
  await page.mouse.click(point.x, point.y);

  const detail = page.locator('.reading-sheet');
  await expect(detail.getByRole('heading', { name: 'Source facts' })).toBeVisible({ timeout: 30_000 });
  await expect(detail.getByText('Location precision', { exact: true })).toBeVisible();
});

test('candidate map retains native overlays and V1 selection across route and basemap changes', async ({ page }) => {
  test.setTimeout(90_000);
  const ready = () => page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return Boolean(map?.isStyleLoaded() && map.isSourceLoaded('locations') && ['clusters', 'aggregate-outer', 'source-coordinate-points', 'v1-source-pins'].every(id => map.getLayer(id)));
  }, undefined, { timeout: 60_000 });
  await page.goto('/v2-preview/#/map?f1a=field&source=us.fsis');
  await ready();
  const first = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return {
      sourceCount: map.querySourceFeatures('locations').length,
      referencePaint: map.getPaintProperty('aggregate-outer', 'circle-stroke-color'),
      coordinateColor: map.getPaintProperty('source-coordinate-points', 'circle-color'),
    };
  });
  expect(first.sourceCount).toBeGreaterThan(0);
  expect(first.referencePaint).toBe('#ff695c');
  expect(first.coordinateColor).toBeTruthy();

  await page.getByRole('button', { name: 'Tools' }).click();
  await page.getByLabel('Enable debug menu').check();
  await page.getByRole('button', { name: 'Debug menu' }).click();
  await page.getByLabel('Use V1 facility pin PNG + shadow').check();
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getLayoutProperty('v1-source-pins', 'visibility') === 'visible');
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const sourceFeature = map.querySourceFeatures('locations').find((feature: any) => feature.properties?.kind === 'source-coordinate');
    map.jumpTo({ center: sourceFeature.geometry.coordinates, zoom: 14 });
  });
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.queryRenderedFeatures({ layers: ['v1-source-pins'] }).length > 0, undefined, { timeout: 30_000 });
  const point = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const feature = map.queryRenderedFeatures({ layers: ['v1-source-pins'] })[0];
    const coordinate = map.project(feature.geometry.coordinates);
    const bounds = map.getContainer().getBoundingClientRect();
    return { x: bounds.left + coordinate.x, y: bounds.top + coordinate.y };
  });
  await page.mouse.click(point.x, point.y);
  await expect(page.locator('.reading-sheet').getByRole('heading', { name: 'Source facts' })).toBeVisible({ timeout: 30_000 });

  await page.goto('/v2-preview/#/database?f1a=field&source=us.fsis');
  await page.goto('/v2-preview/#/map?f1a=field&source=us.fsis');
  await ready();
  await page.getByLabel('Map style').selectOption('muted');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.getPaintProperty('base', 'raster-saturation') === -1 && map.isSourceLoaded('locations') && ['clusters', 'aggregate-outer', 'source-coordinate-points', 'v1-source-pins'].every(id => map.getLayer(id));
  }, undefined, { timeout: 30_000 });
  await page.getByLabel('Map style').selectOption('vector');
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPaintProperty('base', 'raster-saturation') === 0);
  await page.getByLabel('Map style').selectOption('satellite');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isSourceLoaded('locations') && ['clusters', 'aggregate-outer', 'source-coordinate-points', 'v1-source-pins'].every(id => map.getLayer(id));
  }, undefined, { timeout: 30_000 });
});

test('candidate map keeps mobile controls clear and uses category and reference paints', async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/v2-preview/#/map?f1a=field');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return Boolean(map?.isStyleLoaded() && map.isSourceLoaded('locations') && map.getLayer('aggregate-outer'));
  }, undefined, { timeout: 60_000 });
  const paints = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return {
      coordinate: JSON.stringify(map.getPaintProperty('source-coordinate-points', 'circle-color')),
      reference: map.getPaintProperty('aggregate-outer', 'circle-color'),
      opacity: JSON.stringify(map.getPaintProperty('aggregate-outer', 'circle-opacity')),
      stroke: map.getPaintProperty('aggregate-outer', 'circle-stroke-color'),
    };
  });
  expect(paints.coordinate).toContain('#009E73');
  expect(paints.coordinate).toContain('#0072B2');
  expect(paints.reference).toBe('#d8473f');
  expect(paints.opacity).toContain('0.22');
  expect(paints.stroke).toBe('#ff695c');

  await page.getByRole('button', { name: 'Search map' }).click();
  await page.locator('details.filters > summary').click();
  await expect(page.getByRole('group', { name: 'Country' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('group', { name: 'Source' })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Activity category' })).toBeVisible();
  const controlsDoNotOverlap = await page.evaluate(() => {
    const picker = document.querySelector('.basemap-picker')?.getBoundingClientRect();
    const attribution = document.querySelector('.maplibregl-ctrl-attrib')?.getBoundingClientRect();
    return !picker || !attribution || picker.bottom <= attribution.top || attribution.bottom <= picker.top || picker.right <= attribution.left || attribution.right <= picker.left;
  });
  expect(controlsDoNotOverlap).toBe(true);
});

test('plain map entry uses the configured candidate projection and preserves its map controls', async ({ page }) => {
  test.setTimeout(120_000);
  const candidateRequests: string[] = [];
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith('/api/dev/preview/test-release/')) candidateRequests.push(path);
  });
  await page.goto('/v2-preview/#/map');
  await page.evaluate(async () => Promise.all((await caches.keys()).map(name => caches.delete(name))));
  await page.reload();
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return document.querySelector('.lab')?.getAttribute('data-data-mode') === 'candidate-preview'
      && Boolean(map?.isStyleLoaded() && map.isSourceLoaded('locations') && map.getLayer('aggregate-outer'));
  }, undefined, { timeout: 90_000 });
  const mapState = await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const features = map.getSource('locations').serialize().data.features;
    const reference = features.find((feature: any) => feature.properties?.kind === 'reference');
    const approximate = features.find((feature: any) => feature.properties?.kind === 'source-coordinate' && ['approximate', 'city', 'source_reported', 'source_provided_unverified', 'city_reference_approximate', 'provider_locality_approximate', 'locality_reference_coarse'].includes(feature.properties?.precision));
    const target = reference ?? approximate;
    if (target) {
      map.jumpTo({ center: target.geometry.coordinates, zoom: 9 });
      await new Promise<void>(resolve => map.once('idle', resolve));
    }
    return {
      color: JSON.stringify(map.getPaintProperty('source-coordinate-points', 'circle-color')),
      referenceColor: map.getPaintProperty('aggregate-outer', 'circle-color'),
      referenceStroke: map.getPaintProperty('aggregate-outer', 'circle-stroke-color'),
      referenceOpacity: JSON.stringify(map.getPaintProperty('aggregate-outer', 'circle-opacity')),
      v1Icons: JSON.stringify(map.getLayoutProperty('v1-source-pins', 'icon-image')),
      renderedReferences: map.queryRenderedFeatures({ layers: ['aggregate-outer'] }).length,
      hasApproximatePoint: Boolean(approximate),
    };
  });
  expect(mapState.color).toContain('#009E73');
  expect(mapState.color).toContain('#0072B2');
  expect(mapState.referenceColor).toBe('#d8473f');
  expect(mapState.referenceStroke).toBe('#ff695c');
  expect(mapState.referenceOpacity).toContain('0.22');
  expect(mapState.v1Icons).toContain('v1-pin-green');
  expect(mapState.v1Icons).toContain('v1-pin-yellow');
  expect(mapState.hasApproximatePoint).toBe(true);
  expect(mapState.renderedReferences).toBeGreaterThan(0);

  await page.getByRole('button', { name: 'Search map' }).click();
  await page.locator('details.filters > summary').click();
  await expect(page.getByRole('group', { name: 'Country' })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('group', { name: 'Source' })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('group', { name: 'Activity category' })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('group', { name: 'Activity', exact: true })).toBeVisible({ timeout: 60_000 });
  expect(candidateRequests).toContain('/api/dev/preview/test-release/map/feed');
  expect(candidateRequests).toContain('/api/dev/preview/test-release/discovery/facets');
  await page.goto('/v2-preview/#/database');
  await page.goto('/v2-preview/#/map');
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.isSourceLoaded('locations'), undefined, { timeout: 60_000 });

  await page.getByRole('button', { name: 'Tools' }).click();
  await page.getByLabel('Enable debug menu').check();
  await page.getByRole('button', { name: 'Debug menu' }).click();
  await page.getByLabel('Use V1 facility pin PNG + shadow').check();
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getLayoutProperty('v1-source-pins', 'visibility') === 'visible');
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const feature = map.querySourceFeatures('locations').find((item: any) => item.properties?.kind === 'source-coordinate');
    map.jumpTo({ center: feature.geometry.coordinates, zoom: 14 });
  });
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.queryRenderedFeatures({ layers: ['v1-source-pins'] }).length > 0, undefined, { timeout: 30_000 });
  const point = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const feature = map.queryRenderedFeatures({ layers: ['v1-source-pins'] })[0];
    const point = map.project(feature.geometry.coordinates);
    const box = map.getContainer().getBoundingClientRect();
    return { x: box.left + point.x, y: box.top + point.y };
  });
  await page.mouse.click(point.x, point.y);
  await expect(page.locator('.reading-sheet').getByRole('heading', { name: 'Source facts' })).toBeVisible({ timeout: 30_000 });

  const annualRecordId = await page.evaluate(async () => {
    const facetsResponse = await fetch('/api/dev/preview/test-release/discovery/facets', { cache: 'no-store' });
    if (!facetsResponse.ok) throw new Error('Candidate facets were unavailable while locating annual evidence.');
    const facets = await facetsResponse.json();
    const source = facets.dimensions.source_id.find((item: { value: string; label?: string }) => /aphis/i.test(`${item.value} ${item.label ?? ''}`));
    if (!source) throw new Error('No APHIS candidate source was available.');
    const listResponse = await fetch(`/api/dev/preview/test-release/locations?profile=official&limit=1000&source_id=${encodeURIComponent(source.value)}`, { cache: 'no-store' });
    if (!listResponse.ok) throw new Error('APHIS candidate list was unavailable.');
    const list = await listResponse.json();
    for (const row of list.data.slice(0, 25)) {
      const detailResponse = await fetch(`/api/dev/preview/test-release/locations/${encodeURIComponent(row.facility_id)}`, { cache: 'no-store' });
      if (!detailResponse.ok) continue;
      const detail = await detailResponse.json();
      if (Array.isArray(detail.data?.aphis_annual_reports) && detail.data.aphis_annual_reports.some((report: { species_counts?: unknown[] }) => Array.isArray(report.species_counts) && report.species_counts.length > 0)) return row.facility_id;
    }
    throw new Error('No matched APHIS annual evidence was returned.');
  });
  await page.goto(`/v2-preview/#/records/${annualRecordId}?f1a=field`);
  await expect(page.getByText(/^FY\d{4} reported animals$/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('link', { name: 'Source report' })).toBeVisible();
});
