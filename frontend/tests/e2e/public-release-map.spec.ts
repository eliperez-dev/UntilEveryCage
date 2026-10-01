import { expect, test, type Page } from '@playwright/test';
import fixture from '../fixtures/release-map/manifest.json' with { type: 'json' };

const recordId = '123e4567-e89b-42d3-a456-426614174000';

function manifest(releaseId: string, generation = 1) {
  const value = structuredClone(fixture) as Record<string, any>;
  value.data.release_id = releaseId;
  value.data.suppression_generation = generation;
  value.data.manifest.map_artifact.release_id = releaseId;
  value.data.manifest.map_artifact.generated_at = '2026-09-29T00:00:00Z';
  value.data.manifest.map_artifact.suppression_generation = generation;
  value.data.manifest.map_artifact.tile_url_template = `/api/v2/releases/${releaseId}/map/tiles/{z}/{x}/{y}.mvt?profile=official`;
  return value;
}

const wireRecord = {
  facility_id: recordId,
  canonical_name: 'Approved Fixture Facility',
  country_code: 'BE',
  city: 'Fixture City',
  category: 'farm',
  taxonomy_display_category: 'slaughter',
  taxonomy_primary_categories: ['slaughter', 'processing_and_preparation'],
  taxonomy_leaf_activities: [
    { key: 'slaughter', label: 'Slaughterhouse' },
    { key: 'processing', label: 'Meat processing' },
  ],
  taxonomy_assignments: [{
    primary_key: 'slaughter', leaf_key: 'slaughter', leaf_label: 'Slaughterhouse',
    source_code_reference: 'activity_codes', source_label_reference: 'activity_descriptions',
    source_code: 'S-1', source_label: 'Slaughterhouse', method: 'direct', status: 'mapped',
    taxonomy_version: 'uec-taxonomy-v1', crosswalk_version: 'crosswalk-v1', ruleset_version: 'ruleset-v1',
  }],
  publication_profile: 'official',
  factual_review_status: 'project-reviewed',
  privacy_screening_status: 'passed',
  project_approval: 'approved',
  reviewer_role: 'maintainer',
  publication_warning: null,
  display_precision: 'exact',
  latitude: 50.85,
  longitude: 4.35,
  first_observed_at: '2026-01-01T00:00:00Z',
  last_observed_at: '2026-01-01T00:00:00Z',
  observation_count: 1,
  lifecycle_status: 'active_observed',
  source_type: 'official',
  source_rights_status: 'cleared',
  provenance_source: null,
  release_id: 'release-a',
  release_ruleset_version: 'rules-v1',
  provenance_source_id: 'fixture.source',
  provenance_source_name: 'Fixture source',
  provenance_source_url: 'https://example.invalid/source',
  provenance_retrieved_at: '2026-01-01T00:00:00Z',
};

function envelope(data: unknown, releaseId: string) {
  return {
    api_version: 'v2',
    data,
    meta: {
      release_id: releaseId,
      ruleset_version: 'rules-v1',
      release_created_at: '2026-01-01T00:00:00Z',
      profile: 'official',
      coverage_note: 'Synthetic browser test fixture.',
      coverage_scope: 'fixture only',
      count_semantics: 'public locations',
      next_cursor: null,
    },
  };
}

function detailEnvelope(data: unknown, releaseId: string) {
  return {
    api_version: 'v2',
    data,
    meta: { release_id: releaseId, ruleset_version: 'rules-v1', release_created_at: '2026-01-01T00:00:00Z', profile: 'official', coverage_scope: 'fixture only', count_semantics: 'public locations' },
  };
}

async function mockBaseTiles(page: Page) {
  const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/F2sAAAAASUVORK5CYII=', 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: pixel }));
  await page.route('https://server.arcgisonline.com/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: pixel }));
  await page.route('**/api/v2/releases/*/map/tiles/**', route => route.fulfill({ status: 200, contentType: 'application/vnd.mapbox-vector-tile', body: Buffer.alloc(0) }));
}

async function waitForSource(page: Page, releaseId: string, generation = 1) {
  const sourceId = `release-${releaseId}-${generation}-source`;
  await page.waitForFunction(id => Boolean((window as any).__UEC_PUBLIC_RELEASE_MAP__?.getSource(id)), sourceId);
}

async function fireFeatureClick(page: Page, feature: Record<string, unknown>, layerId: string) {
  await page.evaluate(({ feature: selected, layerId: targetLayer }) => {
    const map = (window as any).__UEC_PUBLIC_RELEASE_MAP__;
    map.queryRenderedFeatures = () => [{
      type: 'Feature',
      geometry: { type: 'Point', coordinates: (selected.geometry as any).coordinates },
      properties: selected.properties,
      layer: { id: targetLayer, type: 'circle', source: 'fixture', 'source-layer': 'uec_map' },
      source: 'fixture', sourceLayer: 'uec_map', state: {},
    }];
    const MapLibre = (window as any).maplibregl;
    map.fire('click', {
      point: { x: 20, y: 20 },
      lngLat: MapLibre?.LngLat?.convert?.([0, 0]) ?? { lng: 0, lat: 0 },
      originalEvent: new MouseEvent('click'),
    });
  }, { feature, layerId });
}

test('an unavailable release keeps cached map data hidden and never falls back to private or synthetic data', async ({ page }) => {
  const observed: string[] = [];
  await mockBaseTiles(page);
  await page.route(url => new URL(url.href).pathname === '/api/v2/releases/manifest', route => route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }));
  page.on('request', request => observed.push(new URL(request.url()).pathname));
  await page.goto('./#/map');
  await expect(page.getByRole('alert')).toContainText('could not be verified');
  await expect(page.getByLabel('Map of public facilities')).toHaveAttribute('aria-label', 'Map of public facilities');
  await expect(page.getByLabel('Search this release')).toHaveCount(0);
  const state = await page.evaluate(() => {
    const map = (window as any).__UEC_PUBLIC_RELEASE_MAP__;
    return { sources: Object.keys(map?.getStyle?.()?.sources ?? {}), gated: Boolean(document.querySelector('.map.gated')) };
  });
  expect(state.gated).toBe(true);
  expect(state.sources.some((source: string) => source.startsWith('release-'))).toBe(false);
  expect(observed.some(path => path.startsWith('/dev/real-preview/'))).toBe(false);
  expect(observed.some(path => path.includes('/fixtures/'))).toBe(false);
});

test('published layers expand server clusters and resolve exact leaves through release-pinned public search and detail', async ({ page }) => {
  const releaseId = 'release-a';
  const detailRequests: string[] = [];
  await mockBaseTiles(page);
  await page.route(url => new URL(url.href).pathname === '/api/v2/releases/manifest', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(manifest(releaseId)) }));
  await page.route(url => new URL(url.href).pathname === '/api/v2/locations' && new URL(url.href).searchParams.has('q'), route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope([wireRecord], releaseId)) }));
  await page.route(url => new URL(url.href).pathname === `/api/v2/locations/${recordId}`, async route => {
    detailRequests.push(route.request().url());
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(detailEnvelope(wireRecord, releaseId)) });
  });

  await page.goto('./#/map');
  await expect(page.getByLabel('Search this release')).toBeVisible();
  await waitForSource(page, releaseId);

  const initialZoom = await page.evaluate(() => (window as any).__UEC_PUBLIC_RELEASE_MAP__.getZoom());
  await fireFeatureClick(page, {
    geometry: { type: 'Point', coordinates: [4.35, 50.85] },
    properties: { kind: 'cluster', feature_key: 'stable-cluster-key', count: 4, exact_count: 4, coarse_count: 0, next_zoom: 3 },
  }, `release-${releaseId}-1-cluster-circle`);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_PUBLIC_RELEASE_MAP__.getZoom())).toBeGreaterThan(initialZoom);
  const mapLayerChecks = await page.evaluate(() => {
    const map = (window as any).__UEC_PUBLIC_RELEASE_MAP__;
    return ['cluster-circle', 'coarse-area', 'exact-pin'].map(suffix => {
      const layer = map.getLayer(`release-release-a-1-${suffix}`);
      return { suffix, present: Boolean(layer), filter: layer?.filter };
    });
  });
  expect(mapLayerChecks.every(layer => layer.present && Array.isArray(layer.filter))).toBe(true);

  await fireFeatureClick(page, {
    geometry: { type: 'Point', coordinates: [4.35, 50.85] },
    properties: { kind: 'exact', feature_key: 'exact-key', record_id: recordId, count: 1, exact_count: 1, coarse_count: 0 },
  }, `release-${releaseId}-1-exact-pin`);
  await expect(page.getByRole('article', { name: 'Public location detail' })).toContainText('release release-a');
  await expect.poll(() => detailRequests.length).toBe(1);

  await page.getByLabel('Search public locations').fill('fixture');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.getByRole('button', { name: /Approved Fixture Facility/ })).toBeVisible();
  await page.getByRole('button', { name: /Approved Fixture Facility/ }).click();
  await expect(page.getByRole('article', { name: 'Public location detail' })).toContainText('release release-a');
  await expect.poll(() => detailRequests.length).toBe(2);
  const detailUrl = new URL(detailRequests[0]);
  expect(detailUrl.searchParams.get('profile')).toBe('official');
  expect(detailUrl.searchParams.get('release_id')).toBe(releaseId);

  await page.evaluate(() => {
    const map = (window as any).__UEC_PUBLIC_RELEASE_MAP__;
    map.queryRenderedFeatures = () => [{
      type: 'Feature', geometry: { type: 'Point', coordinates: [4.35, 50.85] },
      properties: { kind: 'coarse', feature_key: 'coarse-key', count: 1, coarse_count: 1, exact_count: 0, record_id: null },
      layer: { id: 'release-release-a-1-coarse-area', type: 'circle', source: 'fixture', 'source-layer': 'uec_map' },
      source: 'fixture', sourceLayer: 'uec_map', state: {},
    }];
    map.fire('click', { point: { x: 20, y: 20 }, lngLat: { lng: 4.35, lat: 50.85 }, originalEvent: new MouseEvent('click') });
  });
  await expect.poll(() => detailRequests.length).toBe(2);
  await expect(page.getByText(/Approximate city-level location/)).toHaveCount(0);
  expect(detailRequests.every(url => new URL(url).searchParams.get('release_id') === releaseId)).toBe(true);
});

test('taxonomy search uses OR filters and provenance while category changes stay in the loaded map style', async ({ page }) => {
  const releaseId = 'release-a';
  const processingRecord = {
    ...wireRecord,
    facility_id: '223e4567-e89b-42d3-a456-426614174000',
    canonical_name: 'Processing Fixture Facility',
    taxonomy_display_category: 'processing_and_preparation',
    taxonomy_primary_categories: ['processing_and_preparation'],
    taxonomy_leaf_activities: [{ key: 'processing', label: 'Meat processing' }],
    taxonomy_assignments: [{ ...wireRecord.taxonomy_assignments[0],
      primary_key: 'processing_and_preparation', leaf_key: 'processing', leaf_label: 'Meat processing',
      source_code: 'P-1', source_label: 'Meat processing' }],
  };
  const observed: string[] = [];
  const browserErrors: string[] = [];
  await mockBaseTiles(page);
  page.on('request', request => observed.push(new URL(request.url()).pathname));
  page.on('pageerror', error => browserErrors.push(error.message));
  await page.route(url => new URL(url.href).pathname === '/api/v2/releases/manifest', route => {
    const body = manifest(releaseId);
    body.data.manifest.map_artifact.feature_schema_version = 'uec-map-feature-v2';
    body.data.manifest.map_artifact.feature_properties = [
      'feature_key', 'kind', 'count', 'exact_count', 'coarse_count', 'next_zoom', 'record_id',
      'category_key', 'category_keys_compact',
    ];
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.route(url => new URL(url.href).pathname === '/api/v2/locations' && new URL(url.href).searchParams.has('q'), route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope([wireRecord, processingRecord], releaseId)) }));
  await page.route(url => new URL(url.href).pathname === `/api/v2/locations/${recordId}`, route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(detailEnvelope(wireRecord, releaseId)) }));

  await page.goto('./#/map');
  await expect(page.getByLabel('Search this release')).toBeVisible();
  await waitForSource(page, releaseId);
  await page.getByLabel('Search public locations').fill('fixture');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  const slaughterResult = page.getByRole('button', { name: /Approved Fixture Facility/ });
  const processingResult = page.getByRole('button', { name: /Processing Fixture Facility/ });
  await expect(slaughterResult).toBeVisible();
  await expect(processingResult).toBeVisible();

  const networkBeforeFilters = observed.filter(path => path === '/api/v2/locations').length;
  await page.getByRole('checkbox', { name: /Slaughter/ }).check();
  await expect(slaughterResult).toBeVisible();
  await expect(processingResult).toHaveCount(0);
  await page.getByRole('checkbox', { name: /Processing and preparation/ }).check();
  await expect(slaughterResult).toBeVisible();
  await expect(processingResult).toBeVisible();
  expect(observed.filter(path => path === '/api/v2/locations')).toHaveLength(networkBeforeFilters);

  const layers = await page.evaluate(() => {
    const map = (window as any).__UEC_PUBLIC_RELEASE_MAP__;
    return {
      exact: map.getFilter('release-release-a-1-exact-pin'),
      clusters: map.getFilter('release-release-a-1-cluster-circle'),
      coarse: map.getFilter('release-release-a-1-coarse-area'),
      sourceType: map.getSource('release-release-a-1-source')?.type,
    };
  });
  expect(JSON.stringify(layers.exact)).toContain('|slaughter|');
  expect(JSON.stringify(layers.exact)).toContain('|processing_and_preparation|');
  expect(layers.clusters).toEqual(['==', ['get', 'kind'], 'cluster']);
  expect(layers.coarse).toEqual(['==', ['get', 'kind'], 'coarse']);
  expect(layers.sourceType).toBe('vector');

  await slaughterResult.click();
  const detail = page.getByRole('article', { name: 'Public location detail' });
  await expect(detail).toContainText('Activities');
  await expect(detail).toContainText('Slaughterhouse');
  await expect(detail).toContainText('Meat processing');
  await expect(detail).toContainText('Slaughterhouse · direct · mapped · uec-taxonomy-v1');
  expect(browserErrors).toEqual([]);
});

test('release switching removes old layers before validating the replacement and clears data on failure', async ({ page }) => {
  await mockBaseTiles(page);
  let manifestCalls = 0;
  let releaseReplacement!: () => void;
  let replacementStarted = false;
  const replacement = new Promise<void>(resolve => { releaseReplacement = resolve; });
  await page.route(url => new URL(url.href).pathname === '/api/v2/releases/manifest', async route => {
    manifestCalls += 1;
    if (manifestCalls === 1) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(manifest('release-a', 1)) });
    if (manifestCalls === 2) {
      replacementStarted = true;
      await replacement;
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(manifest('release-b', 2)) });
    }
    return route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
  });
  await page.goto('./#/map');
  await waitForSource(page, 'release-a', 1);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => replacementStarted).toBe(true);
  const detachedState = await page.evaluate(() => {
    const sources = Object.keys((window as any).__UEC_PUBLIC_RELEASE_MAP__?.getStyle?.()?.sources ?? {});
    return sources.filter(source => source.startsWith('release-'));
  });
  expect(detachedState).toEqual([]);
  releaseReplacement();
  await waitForSource(page, 'release-b', 2);
  const switched = await page.evaluate(() => Object.keys((window as any).__UEC_PUBLIC_RELEASE_MAP__?.getStyle?.()?.sources ?? {}).filter(source => source.startsWith('release-')));
  expect(switched).toEqual(['release-release-b-2-source']);

  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await expect(page.getByRole('alert')).toContainText('could not be verified');
  const failedState = await page.evaluate(() => Object.keys((window as any).__UEC_PUBLIC_RELEASE_MAP__?.getStyle?.()?.sources ?? {}).filter(source => source.startsWith('release-')));
  expect(failedState).toEqual([]);
});
