import { expect, test } from '@playwright/test';
import { expectNearbyScope } from './nearbyMapAssertions';
import releaseManifest from '../fixtures/release-map/manifest.json' with { type: 'json' };

const exactId = '123e4567-e89b-42d3-a456-426614174000';
const approximateId = '223e4567-e89b-42d3-a456-426614174000';
const fastSearchId = exactId;
const slowSearchId = approximateId;
const releaseId = 'synthetic-release-2026-09';
const exactPoint: [number, number] = [4.35, 50.85];
const approximatePoint: [number, number] = [4.45, 50.95];

function testManifest() {
  const value = structuredClone(releaseManifest) as Record<string, any>;
  value.data.release_id = releaseId;
  value.data.manifest.map_artifact.release_id = releaseId;
  value.data.manifest.map_artifact.tile_url_template = `/api/v2/releases/${releaseId}/map/tiles/{z}/{x}/{y}.mvt?profile=official`;
  return value;
}

test('cold landing entry and warmed reload keep map controls and exact/approximate points interactive', async ({ page, browserName }) => {
  test.setTimeout(60_000);
  test.skip(browserName !== 'chromium', 'The cache-backed map lifecycle regression runs in Chromium.');
  await page.setViewportSize({ width: 1280, height: 900 });

  const feed = {
    api_version: 'v2',
    data: { type: 'FeatureCollection', features: [
      { type: 'Feature', id: exactId, geometry: { type: 'Point', coordinates: exactPoint }, properties: {
        facility_id: exactId, source_id: 'fixture.source', category_key: 'slaughter', category_keys: ['slaughter'], precision: 'exact', weight: 1,
      } },
      { type: 'Feature', id: approximateId, geometry: { type: 'Point', coordinates: approximatePoint }, properties: {
        facility_id: approximateId, source_id: 'fixture.source', category_key: 'slaughter', category_keys: ['slaughter'], precision: 'approximate', weight: 1,
      } },
    ] },
    meta: {
      profile: 'official', release_id: releaseId,
      manifest_sha256: 'a'.repeat(64), suppression_generation: 7,
      feature_count: 2, public_record_count: 2, unmapped_count: 0,
      release_label: 'Synthetic test release', dataset_version: 'synthetic-test',
    },
  };
  const listRows = [
    { facility_id: exactId, canonical_name: 'Exact fixture record', country_code: 'BE', city: 'Fixture A', category: 'slaughter', publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved', reviewer_role: null, publication_warning: null, display_precision: 'exact', latitude: exactPoint[1], longitude: exactPoint[0], first_observed_at: null, last_observed_at: '2026-01-01T00:00:00Z', observation_count: 1, lifecycle_status: 'active_observed', source_type: 'official', source_rights_status: 'cleared', provenance_source: null, provenance_source_id: 'fixture.source', provenance_source_name: 'Fixture source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z', release_id: releaseId, release_ruleset_version: 'rules-v1' },
    { facility_id: approximateId, canonical_name: 'Approximate fixture record', country_code: 'BE', city: 'Fixture B', category: 'slaughter', publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved', reviewer_role: null, publication_warning: null, display_precision: 'approximate', latitude: approximatePoint[1], longitude: approximatePoint[0], first_observed_at: null, last_observed_at: '2026-01-01T00:00:00Z', observation_count: 1, lifecycle_status: 'active_observed', source_type: 'official', source_rights_status: 'cleared', provenance_source: null, provenance_source_id: 'fixture.source', provenance_source_name: 'Fixture source', provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z', release_id: releaseId, release_ruleset_version: 'rules-v1' },
  ];
  const listResponse = (data: unknown[], totalCount = data.length) => ({ api_version: 'v2', data, meta: {
    profile: 'official', release_id: releaseId, ruleset_version: 'rules-v1',
    coverage_note: 'Synthetic browser fixture.', coverage_scope: 'Fixture only',
    count_semantics: 'Public locations', next_cursor: null, total_count: totalCount,
  } });
  const fastSearchRow = { ...listRows[0], facility_id: fastSearchId, canonical_name: 'Fast fixture record' };
  const slowSearchRow = { ...listRows[1], facility_id: slowSearchId, canonical_name: 'Slow fixture record' };
  let releaseSlowList!: () => void;
  let slowListStarted!: () => void;
  const slowListEntered = new Promise<void>(resolve => { slowListStarted = resolve; });
  let slowListFinished!: () => void;
  const slowListCompleted = new Promise<void>(resolve => { slowListFinished = resolve; });
  let releaseSlowMatches!: () => void;
  let slowMatchesStarted!: () => void;
  const slowMatchesEntered = new Promise<void>(resolve => { slowMatchesStarted = resolve; });
  let slowMatchesFinished!: () => void;
  const slowMatchesCompleted = new Promise<void>(resolve => { slowMatchesFinished = resolve; });
  const matchingResponse = (ids: string[]) => ({ api_version: 'v2', data: { facility_ids: ids }, meta: {
    profile: 'official', release_id: releaseId, manifest_sha256: 'a'.repeat(64), suppression_generation: 7,
    total_count: ids.length, mapped_count: ids.length,
  } });
  let feedRequests = 0;
  const tile = Buffer.from(await page.evaluate(() => {
    const canvas=document.createElement('canvas');canvas.width=canvas.height=256;
    const context=canvas.getContext('2d')!;context.fillStyle='#252525';context.fillRect(0,0,256,256);
    return canvas.toDataURL('image/png').split(',')[1]!;
  }), 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: tile }));
  await page.route('https://server.arcgisonline.com/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: tile }));
  await page.route(url => new URL(url.href).pathname === '/api/v2/releases/manifest', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(testManifest()) }));
  await page.route(url => new URL(url.href).pathname === '/api/v2/map/feed', route => {
    feedRequests++;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(feed) });
  });
  await page.route(url => new URL(url.href).pathname === '/api/v2/locations', async route => {
    const q = new URL(route.request().url()).searchParams.get('q');
    if (q === 'slow') {
      slowListStarted();
      await new Promise<void>(resolve => { releaseSlowList = resolve; });
      try { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(listResponse([slowSearchRow])) }); }
      catch { /* The latest query intentionally aborts this stale response. */ }
      finally { slowListFinished(); }
      return;
    }
    const rows = q === 'fast' ? [fastSearchRow] : q === 'no-match' ? [] : listRows;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(listResponse(rows, rows.length)) });
  });
  await page.route(url => new URL(url.href).pathname === '/api/v2/map/matches', async route => {
    const q = new URL(route.request().url()).searchParams.get('q');
    if (q === 'slow') {
      slowMatchesStarted();
      await new Promise<void>(resolve => { releaseSlowMatches = resolve; });
      try { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(matchingResponse([slowSearchId])) }); }
      catch { /* The newer query aborts this stale ID-mask response. */ }
      finally { slowMatchesFinished(); }
      return;
    }
    if (q === 'map-error') { await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }); return; }
    const ids = q === 'fast' ? [fastSearchId] : q === 'no-match' ? [] : [exactId, approximateId];
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(matchingResponse(ids)) });
  });
  await page.route(url => new URL(url.href).pathname === '/api/v2/discovery/facets', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ api_version: 'v2', data: { dimensions: {} }, meta: { profile: 'official', release_id: releaseId, ruleset_version: 'rules-v1' } }),
  }));
  await page.addInitScript(() => {
    (window as any).__coldInitialHash = location.hash;
  });
  const expectMapIds = async (ids: string[]) => {
    await expect.poll(() => page.evaluate(async () => {
      const source = (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('locations');
      const data = await source.getData();
      return data.features.map((feature: any) => feature.properties.facility_id).sort();
    })).toEqual([...ids].sort());
  };
  const expectMapWidth = async () => {
    await expect.poll(() => page.evaluate(() => {
      const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const expectedWidth = document.querySelector('.workspace')!.getBoundingClientRect().width;
      const widths = [current.getCanvas().getBoundingClientRect().width, current.getContainer().getBoundingClientRect().width, document.querySelector('.map-stage')!.getBoundingClientRect().width];
      return Math.max(...widths.map(width => Math.abs(width - expectedWidth)));
    })).toBeLessThan(1);
  };
  const expectSelectedCentered = async (point: [number, number]) => {
    await expect.poll(() => page.evaluate((coordinate) => {
      const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const pixel = current.project(coordinate);
      const canvas = current.getCanvas().getBoundingClientRect();
      return Math.hypot(pixel.x - canvas.width / 2, pixel.y - canvas.height / 2);
    }, point)).toBeLessThan(1);
  };

  // A direct site load starts at the separate landing before map entry.
  await page.goto('./');
  expect(await page.evaluate(() => (window as any).__coldInitialHash)).toBe('');
  await page.getByRole('link', { name: 'Open the map', exact: true }).first().click();
  await page.waitForFunction(() => {
    const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return current?.isStyleLoaded() && current.getSource('locations');
  });

  const search = page.getByRole('button', { name: /Search map/ });
  await expect(search).toBeVisible();
  await search.click();
  await expectMapWidth();
  await expect(page.getByRole('combobox', { name: 'Search across public release records' })).toBeVisible();
  await expect(page.getByText('Exact fixture record')).toBeVisible();
  const searchBox = page.getByRole('combobox', { name: 'Search across public release records' });
  await searchBox.fill('slow');
  await expect(page.getByText('Searching · showing previous results')).toBeVisible();
  await expect(page.getByText('Exact fixture record')).toBeVisible();
  await slowListEntered;
  await slowMatchesEntered;
  await expectMapIds([]); // Pending matching must not show all or stale pins.
  await searchBox.fill('fast');
  await expect(page.getByText('Fast fixture record')).toBeVisible();
  await expectMapIds([fastSearchId]);
  releaseSlowList();
  releaseSlowMatches();
  await Promise.all([slowListCompleted, slowMatchesCompleted]);
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByText('Slow fixture record')).toHaveCount(0);
  await expectMapIds([fastSearchId]);
  await searchBox.fill('no-match');
  await expect(page.getByRole('complementary', { name: 'Search, filters, and results' }).getByText('No records match this search and these filters.')).toBeVisible();
  await expectMapIds([]);
  await searchBox.fill('map-error');
  await expect(page.getByRole('complementary', { name: 'Search, filters, and results' }).getByText('Matching map locations could not be loaded. Try again.')).toBeVisible();
  await expectMapIds([]); // A failed mask must also remain empty.
  await searchBox.fill('');
  await expect(page.getByText('Exact fixture record')).toBeVisible();
  await expectMapIds([exactId, approximateId]);
  expect(new URL(page.url()).hash).toContain('list=open');
  await page.getByRole('button', { name: 'Close workspace', exact: true }).click();
  await expectMapWidth();

  await page.locator('.map-navigation').getByRole('switch', { name: 'Map style: Street', exact: true }).click();
  await expect.poll(() => new URL(page.url()).hash).toContain('basemap=satellite');
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getLayer('approx-reference-pins')))).toBe(true);
  await expect(page.locator('.startup-status')).toHaveCount(0);

  // Destroy and recreate the map through the real route lifecycle.
  const primary = page.getByRole('navigation', { name: 'Primary' });
  await primary.getByRole('link', { name: 'Data', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Data' })).toBeVisible();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Map' }).click();
  await page.waitForFunction(() => {
    const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return current?.isStyleLoaded() && current.getSource('locations');
  });

  // Reload the direct root in the same browser context: Cache Storage is now
  // warm, and entering through the landing must still initialize the controls.
  await page.evaluate(() => history.replaceState(history.state, '', `${location.pathname}${location.search}`));
  await page.reload();
  expect(await page.evaluate(() => (window as any).__coldInitialHash)).toBe('');
  await page.getByRole('link', { name: 'Open the map', exact: true }).first().click();
  await page.waitForFunction(() => {
    const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return current?.isStyleLoaded() && current.getSource('locations');
  });
  expect(feedRequests).toBe(1); // The second full load used the persisted public projection cache.
  await page.getByRole('button', { name: /Search map/ }).click();
  await expect(page.getByRole('combobox', { name: 'Search across public release records' })).toBeVisible();
  expect(new URL(page.url()).hash).toContain('list=open');
  await page.getByRole('button', { name: 'Close workspace', exact: true }).click();
  await page.locator('.map-navigation').getByRole('switch', { name: 'Map style: Street', exact: true }).click();
  await expect.poll(() => new URL(page.url()).hash).toContain('basemap=satellite');
  await expect(page.locator('.startup-status')).toHaveCount(0);

  // Both kinds stay individually selectable below the 2,800-record threshold,
  // even at low zoom. The threshold uses the full filtered population.
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ center: [4.4, 50.9], zoom: 4 }));
  await expect.poll(() => page.evaluate(() => {
    const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const keys = current.queryRenderedFeatures({ layers: ['v1-source-pins', 'approx-reference-pins'] })
      .map((feature: any) => feature.properties?.key);
    return current.getSource('locations').getClusterOptions().cluster === false
      && current.queryRenderedFeatures({ layers: ['clusters'] }).length === 0
      && keys.includes('123e4567-e89b-42d3-a456-426614174000')
      && keys.includes('223e4567-e89b-42d3-a456-426614174000');
  })).toBe(true);

  const moveAndCheckFeature = async (id: string, coordinate: [number, number], layer: string) => {
    await page.evaluate(([longitude, latitude]) => {
      const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      current.jumpTo({ center: [longitude, latitude], zoom: 16 });
    }, coordinate);
    await expect.poll(async () => (await page.evaluate(({ id: key, layer: layerId }) => {
      const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return current.queryRenderedFeatures({ layers: [layerId] }).some((feature: any) => feature.properties?.key === key);
    }, { id, layer }))).toBe(true);
    const pixel = await page.evaluate((point) => {
      const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const projected = current.project(point);
      const bounds = current.getCanvas().getBoundingClientRect();
      const x = bounds.left + projected.x;
      const y = bounds.top + projected.y;
      const target = document.elementFromPoint(x, y);
      return { x, y, target: target?.tagName + '.' + (target as HTMLElement | null)?.className, canvas: { left: bounds.left, top: bounds.top, width: bounds.width, height: bounds.height }, projected };
    }, coordinate);
    await page.evaluate(({ id: key, layer: layerId, point }) => {
      const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      (window as any).__coldMapClick = null;
      current.once('click', (event: any) => {
        (window as any).__coldMapClick = current.queryRenderedFeatures(event.point, { layers: [layerId] })
          .some((feature: any) => (feature.properties?.key ?? feature.properties?.id) === key);
      });
    }, { id, layer });
    // V1 icons use a bottom anchor, so click inside the icon body above its
    // geographic anchor. Circle markers are centered on the coordinate.
    await page.mouse.click(pixel.x, pixel.y + (layer === 'v1-source-pins' ? -10 : 0));
    await expect.poll(() => page.evaluate(() => (window as any).__coldMapClick)).toBe(true);
  };

  await moveAndCheckFeature(exactId, exactPoint, 'v1-source-pins');
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${exactId}`);
  await expectMapWidth();
  await expectSelectedCentered(exactPoint);
  expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('approximate-reference-area')._data.geojson.features)).toHaveLength(0);
  await page.getByRole('button', { name: 'Close record detail' }).click();
  await expect.poll(() => new URL(page.url()).hash).not.toContain(`selected=${exactId}`);
  await page.getByRole('button', { name: 'Close workspace', exact: true }).click();
  await expectMapWidth();
  await expectSelectedCentered(exactPoint);

  await page.evaluate((point) => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ center: point, zoom: 16 }), approximatePoint);
  await expect.poll(() => page.evaluate((id) => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.queryRenderedFeatures({ layers: ['approx-reference-cue'] }).some((feature: any) => feature.properties?.key === id)
      && map.getLayoutProperty('approx-reference-cue', 'icon-image') === 'approximation-mark'
      && map.hasImage('approximation-mark');
  }, approximateId)).toBe(true);
  await moveAndCheckFeature(approximateId, approximatePoint, 'approx-reference-pins');
  await expect.poll(() => page.evaluate((id) => (window as any).__UEC_LOCAL_PREVIEW_MAP__
    .queryRenderedFeatures({ layers: ['approx-reference-cue'] })
    .some((feature: any) => feature.properties?.key === id), approximateId)).toBe(true);
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${approximateId}`);
  await expect.poll(() => page.evaluate((id) => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const area = map.getSource('approximate-reference-area')._data.geojson.features;
    return area.length === 1 && area[0].properties.key === id
      && map.queryRenderedFeatures({ layers: ['approximate-reference-area-fill'] }).some((feature: any) => feature.properties.key === id);
  }, approximateId)).toBe(true);
  const radiusAtZoom = async (zoom: number) => {
    await page.evaluate(({ zoom, point }) => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ center: point, zoom }), { zoom, point: approximatePoint });
    return page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const feature = map.getSource('approximate-reference-area')._data.geojson.features[0];
      const pin = map.queryRenderedFeatures({ layers: ['approx-reference-pins'] })[0];
      const center = map.project(pin.geometry.coordinates);
      const edge = map.project(feature.geometry.coordinates[0][0]);
      return { radius: Math.hypot(edge.x - center.x, edge.y - center.y), ring: feature.geometry.coordinates[0] };
    });
  };
  const radiusAt15 = await radiusAtZoom(15);
  const radiusAt15_5 = await radiusAtZoom(15.5);
  const radiusAt17 = await radiusAtZoom(17);
  expect(radiusAt15.radius).toBeGreaterThan(0);
  expect(radiusAt15_5.radius / radiusAt15.radius).toBeCloseTo(Math.sqrt(2), 1);
  expect(radiusAt17.radius / radiusAt15.radius).toBeCloseTo(4, 0);
  expect(radiusAt15_5.ring).toEqual(radiusAt15.ring);
  expect(radiusAt17.ring).toEqual(radiusAt15.ring);
  await page.getByRole('button', { name: 'Close record detail' }).click();
  await page.getByRole('button', { name: 'Close workspace', exact: true }).click();
  await expectMapWidth();
  await expectSelectedCentered(approximatePoint);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('approximate-reference-area')._data.geojson.features.length)).toBe(0);
  await page.mouse.move(1, 1);
  await page.waitForTimeout(2600);
  await expect.poll(() => page.evaluate((id) => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map.getSource('approximate-reference-area')._data.geojson.features.length === 0
      && !map.queryRenderedFeatures({ layers: ['approximate-reference-area-fill'] }).some((feature: any) => feature.properties.key === id);
  }, approximateId)).toBe(true);
  expect(feedRequests).toBe(1);

  const navigation = page.getByRole('navigation', { name: 'Map navigation', exact: true });
  await expect(navigation.getByRole('button',{name:'More map controls',exact:true})).toHaveCount(0);
  await expect(navigation.getByRole('button',{name:'Zoom out',exact:true})).toHaveCount(0);
  await navigation.getByRole('button',{name:'View',exact:true}).click();
  await navigation.getByRole('switch',{name:'Map style: Street',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__UEC_LOCAL_PREVIEW_MAP__.getStyle().sources.base.tiles[0])).toContain('World_Imagery');
  await navigation.getByRole('button',{name:'View',exact:true}).click();
  await navigation.getByRole('switch',{name:'Map style: Satellite',exact:true}).click();
  await expect(navigation.getByRole('button',{name:'Switch to 3D',exact:true})).toBeEnabled();
  // Native camera gestures remain supported; the toolbar uses the terrain-aware
  // shared request handler when returning to an overhead view.
  await page.evaluate(()=>(window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({pitch:30}));
  await navigation.getByRole('button',{name:'Switch to 2D',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__UEC_LOCAL_PREVIEW_MAP__.getPitch())).toBe(0);

  // Synthetic browser position only. The app must never request location on load,
  // or serialize the device-derived view into any navigation link or history URL.
  const beforeLocate = new URLSearchParams(new URL(page.url()).hash.split('?')[1]);
  await page.context().grantPermissions(['geolocation']);
  await page.context().setGeolocation({ latitude: 12.345678, longitude: 98.765432 });
  await navigation.getByRole('button', { name: 'Your location', exact: true }).click();
  await expectNearbyScope(page, { latitude: 12.345678, longitude: 98.765432 });
  const canvas=(await page.locator('.maplibregl-canvas').boundingBox())!;
  await page.mouse.move(canvas.x+canvas.width/2,canvas.y+canvas.height/2);
  await page.mouse.wheel(0,120);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getZoom())).toBeLessThan(12);
  const privateViewUrl = new URLSearchParams(new URL(page.url()).hash.split('?')[1]);
  expect(privateViewUrl.get('lat')).toBe(beforeLocate.get('lat'));
  expect(privateViewUrl.get('lon')).toBe(beforeLocate.get('lon'));
  await expect(page.getByRole('button', { name: /Search map/ })).toBeVisible();
  await page.getByRole('button', { name: /Search map/ }).click();
  await expect(page.getByRole('button', { name: 'Saved searches', exact: true })).toHaveCount(0);
  const links = await page.locator('a[href]').evaluateAll(elements => elements.map(element => element.getAttribute('href')).join('\n'));
  expect(links).not.toMatch(/12\.345678|98\.765432/);
  expect(feedRequests).toBe(1);

  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByLabel('Enable debug menu', { exact: true }).check();
  await page.getByRole('button', { name: 'Close more tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  const debug = page.getByRole('complementary', { name: 'Debug menu', exact: true });
  await expect(debug).toBeVisible();
  await debug.locator('#debug-panel-width').press('End');
  await expectMapWidth();
  await expect.poll(()=>page.evaluate(()=>document.querySelector('.results')!.getBoundingClientRect().width/document.querySelector('.workspace')!.getBoundingClientRect().width)).toBeCloseTo(.55,2);
  await debug.locator('summary').filter({ hasText: 'Map tuning' }).click();
  await debug.locator('#cluster-mode').selectOption('off');
  await expect(debug.locator('#cluster-mode')).toHaveValue('off');
  await debug.locator('#pin-scale').press('End');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getLayoutProperty('v1-source-pins', 'icon-size'))).toBeCloseTo(.8);
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await debug.getByRole('button', { name: 'Copy diagnostics', exact: true }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  const report = JSON.parse(copied);
  expect(report.schema).toBe('uec-map-diagnostics-v1');
  expect(report.viewport).not.toHaveProperty('centerLat');
  expect(copied).not.toMatch(/12\.345678|98\.765432/);
  expect(copied).not.toContain(exactId);
  expect(report.tuning.panelWidthPercent).toBe(55);
  await debug.getByRole('button', { name: 'Reset temporary settings', exact: true }).click();
  await expectMapWidth();
  await expect(debug.locator('#cluster-mode')).toHaveValue('auto');
  await debug.getByRole('button', { name: 'Close debug menu', exact: true }).click();
});
