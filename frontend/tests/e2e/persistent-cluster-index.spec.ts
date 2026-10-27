import { expect, test, type Page } from '@playwright/test';
import releaseManifest from '../fixtures/release-map/manifest.json' with { type: 'json' };

// Actual records must not become test output or trace artifacts.
if (process.env.UEC_REAL_INDEX_ACCEPTANCE === 'true') test.use({ trace: 'off', screenshot: 'off', video: 'off' });

const DATABASE = 'uec-public-cluster-index-v1';
const QUERY = 'synthetic sensitive query';
const INITIAL_RELEASE = 'synthetic-release-2026-09';
const pointCount = 3200;
const id = (index: number) => `123e4567-e89b-42d3-a456-${index.toString(16).padStart(12, '0')}`;
const mapUrl = (release = INITIAL_RELEASE) => `./#/map?release_id=${release}&lat=50.952&lon=4.452&z=8`;

async function fixture(page: Page) {
  const identity = { release: INITIAL_RELEASE, manifest: 'a'.repeat(64), restriction: 7 };
  const features = Array.from({ length: pointCount }, (_, index) => ({
    type: 'Feature', id: id(index), geometry: { type: 'Point', coordinates: [4.45 + index % 80 * .00005, 50.95 + Math.floor(index / 80) * .0001] },
    properties: { facility_id: id(index), source_id: 'fixture.source', category_key: 'slaughter', category_keys: ['slaughter'], precision: 'source_reported', weight: 1 },
  }));
  await page.addInitScript(() => {
    (window as any).__indexEvents = [];
    const channel = new BroadcastChannel('uec-public-cluster-index-diagnostics-v1');
    channel.onmessage = event => { if (typeof event.data?.state === 'string') (window as any).__indexEvents.push(event.data); };
    (window as any).__indexChannel = channel;
  });
  const tile = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/F2sAAAAASUVORK5CYII=', 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ contentType: 'image/png', body: tile }));
  await page.route('https://server.arcgisonline.com/**', route => route.fulfill({ contentType: 'image/png', body: tile }));
  await page.route(url => url.pathname === '/api/v2/releases/manifest', route => {
    const manifest = structuredClone(releaseManifest);
    manifest.data.release_id = identity.release;
    manifest.data.manifest_sha256 = identity.manifest;
    manifest.data.suppression_generation = identity.restriction;
    manifest.data.manifest.map_artifact.release_id = identity.release;
    manifest.data.manifest.map_artifact.suppression_generation = identity.restriction;
    manifest.data.manifest.map_artifact.tile_url_template = `/api/v2/releases/${identity.release}/map/{z}/{x}/{y}.mvt`;
    return route.fulfill({ json: manifest });
  });
  await page.route(url => url.pathname === '/api/v2/map/feed', route => route.fulfill({ json: {
    api_version: 'v2', data: { type: 'FeatureCollection', features }, meta: {
      profile: 'official', release_id: identity.release, manifest_sha256: identity.manifest, suppression_generation: identity.restriction,
      feature_count: pointCount, public_record_count: pointCount, unmapped_count: 0, release_label: 'Synthetic index fixture', dataset_version: 'synthetic-test',
    },
  } }));
  await page.route(url => url.pathname === '/api/v2/locations', route => route.fulfill({ json: {
    api_version: 'v2', data: [{ facility_id: id(0), canonical_name: 'Synthetic cluster facility', country_code: 'BE', city: 'Synthetic place',
      category: 'slaughter', publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed',
      project_approval: 'approved', reviewer_role: null, publication_warning: null, display_precision: 'source_reported',
      latitude: 50.95, longitude: 4.45, first_observed_at: null, last_observed_at: null, observation_count: 1,
      lifecycle_status: 'active_observed', source_type: 'official', source_rights_status: 'cleared', provenance_source: null,
      provenance_source_id: 'fixture.source', provenance_source_name: 'Synthetic source', provenance_source_url: 'https://example.test/source',
      provenance_retrieved_at: '2026-01-01T00:00:00Z', release_id: identity.release, release_ruleset_version: 'rules-v1' }],
    meta: { profile: 'official', release_id: identity.release, ruleset_version: 'rules-v1', coverage_note: 'Synthetic fixture only.',
      next_cursor: null, total_count: new URL(route.request().url()).searchParams.has('q') ? 3000 : pointCount },
  } }));
  await page.route(url => url.pathname === '/api/v2/map/matches', route => route.fulfill({ json: {
    api_version: 'v2', data: { facility_ids: features.slice(0, 3000).map(feature => feature.id) }, meta: {
      profile: 'official', release_id: identity.release, manifest_sha256: identity.manifest, suppression_generation: identity.restriction,
      total_count: 3000, mapped_count: 3000,
    },
  } }));
  await page.route(url => url.pathname === '/api/v2/discovery/facets', route => route.fulfill({ json: {
    api_version: 'v2', data: { dimensions: {} }, meta: { profile: 'official', release_id: identity.release, ruleset_version: 'rules-v1' },
  } }));
  return identity;
}

async function diagnostics(page: Page) {
  if (!await page.locator('#map-diagnostics').isVisible()) {
    await page.getByRole('button', { name: 'More tools', exact: true }).click();
    await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
    await page.getByRole('button', { name: 'Close more tools', exact: true }).click();
    await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  }
  const renderer = page.locator('#map-diagnostics details').filter({ has: page.locator('summary', { hasText: 'Renderer & timing' }) });
  if (!await renderer.evaluate(node => (node as HTMLDetailsElement).open)) await renderer.locator('summary').click();
}

function metric(page: Page, name: string) {
  return page.locator('#map-diagnostics dt').filter({ hasText: new RegExp(`^${name}$`) }).locator('..').locator('dd');
}

async function ready(page: Page, state: 'stored' | 'restored', count = '1 / 0', publicBundle = false) {
  await expect.poll(() => page.evaluate(expected => (window as any).__indexEvents?.some((event: any) => event.state === expected), state), { timeout: 20_000 }).toBe(true);
  if (!publicBundle) await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return Boolean(map?.getLayer('clusters') && map.queryRenderedFeatures({ layers: ['clusters'] }).length);
  }), { timeout: 20_000 }).toBe(true);
  await diagnostics(page);
  if (publicBundle) {
    await expect(page.locator('.startup-status')).toHaveCount(0);
    await expect.poll(async () => Number(await metric(page, 'Rendered marks').innerText())).toBeGreaterThan(0);
  }
  await expect(metric(page, 'Persistent index')).toHaveText(state);
  await expect(metric(page, 'Cache builds / restores')).toHaveText(count);
}

async function storedSummary(page: Page) {
  return page.evaluate(async database => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => { const request = indexedDB.open(database, 1); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); });
    try {
      return await new Promise<{ keys: IDBValidKey[]; key: string; serialized: string }>((resolve, reject) => {
        const transaction = db.transaction('index', 'readonly'), store = transaction.objectStore('index');
        const keys = store.getAllKeys(), active = store.get('active');
        transaction.oncomplete = () => resolve({ keys: keys.result, key: active.result?.key, serialized: JSON.stringify(active.result) });
        transaction.onerror = () => reject(transaction.error);
      });
    } finally { db.close(); }
  }, DATABASE);
}

async function clusterSnapshot(page: Page, expected: number) {
  return page.evaluate(async count => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const feature = map.queryRenderedFeatures({ layers: ['clusters'] }).find((item: any) => item.properties.representedCount === count);
    if (!feature) return null;
    const source = map.getSource('locations'), clusterId = feature.properties.cluster_id;
    return { coordinates: feature.geometry.coordinates, properties: feature.properties,
      expansion: await source.getClusterExpansionZoom(clusterId), children: await source.getClusterChildren(clusterId),
      leaves: (await source.getClusterLeaves(clusterId, 10000, 0)).map((leaf: any) => leaf.properties.facility_id).sort() };
  }, expected);
}

test('hard reload restores the built cluster hierarchy and invalidates changed release identities', async ({ page }) => {
  test.setTimeout(120_000);
  const identity = await fixture(page);
  await page.goto(mapUrl());
  await ready(page, 'stored');
  const cold = await clusterSnapshot(page, pointCount);
  expect(cold?.leaves).toHaveLength(pointCount);
  const originalKey = (await storedSummary(page)).key;
  expect(originalKey).toMatch(/^[a-f0-9]{64}$/);
  await page.reload();
  await ready(page, 'restored', '0 / 1');
  expect(await clusterSnapshot(page, pointCount)).toEqual(cold);
  expect(await page.evaluate(() => (window as any).__indexEvents.some((event: any) => event.state === 'building'))).toBe(false);
  await expect(page.getByText('Building cluster index', { exact: false })).toHaveCount(0);

  // The restored native source still supports the actual cluster-click workflow.
  await page.getByRole('button', { name: 'Close debug menu', exact: true }).click();
  const pixel = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, feature = map.queryRenderedFeatures({ layers: ['clusters'] })[0];
    const point = map.project(feature.geometry.coordinates), box = map.getCanvas().getBoundingClientRect();
    return { x: box.x + point.x, y: box.y + point.y };
  });
  await page.mouse.click(pixel.x, pixel.y);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getZoom())).toBeGreaterThanOrEqual(cold!.expansion);

  let previous = originalKey;
  for (const change of ['restriction', 'manifest', 'release'] as const) {
    if (change === 'restriction') identity.restriction++;
    if (change === 'manifest') identity.manifest = 'c'.repeat(64);
    if (change === 'release') identity.release = 'synthetic-release-2026-10';
    await page.goto(mapUrl(identity.release));
    await page.reload();
    await ready(page, 'stored');
    const current = await storedSummary(page);
    expect(current.key).toMatch(/^[a-f0-9]{64}$/);
    expect(current.key).not.toBe(previous);
    expect(current.keys.filter(key => key !== 'epoch')).toEqual(['active']);
    previous = current.key;
  }
});

test('filter membership and radius change the cache, and corrupt persisted data rebuilds safely', async ({ page }) => {
  test.setTimeout(120_000);
  await fixture(page);
  await page.goto(mapUrl());
  await ready(page, 'stored');
  const fullKey = (await storedSummary(page)).key;
  await page.getByRole('button', { name: 'Close debug menu', exact: true }).click();
  await page.getByRole('button', { name: /Search map/ }).click();
  await page.locator('#field-search').fill(QUERY);
  await expect.poll(() => clusterSnapshot(page, 3000)).not.toBeNull();
  await diagnostics(page);
  await expect(metric(page, 'Persistent index')).toHaveText('stored');
  const filtered = await storedSummary(page);
  expect(filtered.key).not.toBe(fullKey);
  expect(filtered.serialized).not.toContain(QUERY);
  expect(filtered.key).toMatch(/^[a-f0-9]{64}$/);
  expect(filtered.keys.filter(key => key !== 'epoch')).toEqual(['active']);

  await page.locator('#map-diagnostics summary').filter({ hasText: 'Map tuning' }).click();
  await page.locator('#cluster-radius').press('ArrowRight');
  await expect.poll(async () => (await storedSummary(page)).key).not.toBe(filtered.key);
  const radiusKey = (await storedSummary(page)).key;
  await expect(metric(page, 'Persistent index')).toHaveText('stored');
  expect(radiusKey).toMatch(/^[a-f0-9]{64}$/);

  // A full reload intentionally clears in-memory query/radius settings. Persist
  // the default index again, corrupt its built buffer, then require a cold build.
  await page.reload();
  await ready(page, 'stored');
  await page.evaluate(async database => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => { const request = indexedDB.open(database, 1); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); });
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = db.transaction('index', 'readwrite'), store = transaction.objectStore('index'), request = store.get('active');
        request.onsuccess = () => { const entry = request.result; entry.snapshot.buffers[0] = new ArrayBuffer(2); store.put(entry, 'active'); };
        transaction.oncomplete = () => resolve(); transaction.onerror = () => reject(transaction.error);
      });
    } finally { db.close(); }
  }, DATABASE);
  await page.reload();
  await ready(page, 'stored');
  expect((await clusterSnapshot(page, pointCount))?.leaves).toHaveLength(pointCount);

  // Device-derived camera sessions bypass persistent index writes. An explicit
  // area search still applies its membership in memory without storing bounds.
  await page.getByRole('button', { name: 'Close debug menu', exact: true }).click();
  const device = { latitude: 50.9521234567, longitude: 4.4527654321 };
  await page.context().grantPermissions(['geolocation']);
  await page.context().setGeolocation(device);
  await page.getByRole('button', { name: 'Your location', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getCenter().lat)).toBeCloseTo(device.latitude, 7);
  const beforeArea = (await storedSummary(page)).key;
  await page.getByRole('button', { name: 'Search this area', exact: true }).click();
  await expect.poll(() => page.evaluate(async () => {
    const data = await (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('locations').getData();
    return data.features.length;
  })).toBe(3000);
  const area = await storedSummary(page);
  expect(area.key).toBe(beforeArea);
  expect(area.serialized).not.toContain(String(device.latitude));
  expect(area.serialized).not.toContain(String(device.longitude));
  expect(area.serialized).not.toContain(QUERY);
  expect(area.serialized).not.toMatch(/"(?:query|bbox|scope|viewport|navigationViewport)"/);
});

test('cache controls disable writes and clear persisted indexes without clearing the live map', async ({ page }) => {
  test.setTimeout(60_000);
  await fixture(page);
  await page.goto(mapUrl());
  await ready(page, 'stored');
  const initial = await storedSummary(page);
  await page.locator('#map-diagnostics summary').filter({ hasText: 'Cache controls' }).click();
  await page.getByRole('checkbox', { name: 'Persist built index', exact: true }).uncheck();
  await page.locator('#map-diagnostics summary').filter({ hasText: 'Map tuning' }).click();
  await page.locator('#cluster-radius').press('ArrowRight');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('locations').getClusterOptions().clusterRadius)).toBe(55);
  expect((await storedSummary(page)).key).toBe(initial.key);
  await expect(metric(page, 'Persistent index')).toHaveText('Disabled');

  await page.getByRole('checkbox', { name: 'Persist built index', exact: true }).check();
  await page.locator('#cluster-radius').press('ArrowRight');
  await expect.poll(async () => (await storedSummary(page)).key).not.toBe(initial.key);
  await expect(metric(page, 'Persistent index')).toHaveText('stored');
  const live = await clusterSnapshot(page, pointCount);
  await page.getByRole('button', { name: 'Clear built index', exact: true }).click();
  await expect.poll(async () => (await storedSummary(page)).keys.includes('active')).toBe(false);
  expect(await clusterSnapshot(page, pointCount)).toEqual(live);

  await page.reload();
  await ready(page, 'stored');
  expect((await clusterSnapshot(page, pointCount))?.leaves).toHaveLength(pointCount);
});

test('rapid native membership updates keep the latest hierarchy when a cached restore is queued', async ({ page }) => {
  test.setTimeout(45_000);
  await fixture(page);
  await page.goto(mapUrl());
  await ready(page, 'stored');
  await page.evaluate(async () => {
    const source = (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('locations');
    const data = await source.getData();
    const latest = { ...data, features: data.features.slice(0, 3000) };
    await source.setData(latest);
    await Promise.all([
      source.setData(latest),
      source.setData({ ...data, features: data.features.slice(0, 3100) }),
      source.setData(latest),
    ]);
  });
  await expect.poll(() => clusterSnapshot(page, 3000)).not.toBeNull();
  expect((await clusterSnapshot(page, 3000))?.leaves).toHaveLength(3000);
  await expect(metric(page, 'Persistent index')).toHaveText('restored');
  expect(await page.evaluate(async () => (await (window as any).__UEC_LOCAL_PREVIEW_MAP__.getSource('locations').getData()).features.length)).toBe(3000);
});

test.describe('read-only actual release persistence', () => {
  test.skip(process.env.UEC_REAL_INDEX_ACCEPTANCE !== 'true', 'Actual API checks require an explicitly selected read-only local service.');
  for (const release of ['release-2026-10-18', 'v0-candidate-2026-10-04-r3']) {
    test(`${release} stores and restores its complete built index on repeated reloads`, async ({ page }) => {
      test.setTimeout(120_000);
      await page.setViewportSize({ width: 1280, height: 900 });
      const profiling = process.env.UEC_INDEX_PROFILE === 'true';
      const legacyFormat = profiling && process.env.UEC_INDEX_PROFILE_FORMAT === 'legacy';
      const nativeTransport = profiling && process.env.UEC_INDEX_PROFILE_TRANSPORT === 'native';
      if (profiling) {
        await page.route(url => url.pathname.endsWith('/src/map/installPublicMapSourceTransport.ts'), async route => {
          const response = await route.fetch();
          let body = await response.text();
          if (nativeTransport) {
            const pattern = /installPublicMapTransport\(GeoJSONSource\.prototype\);/g;
            expect(body.match(pattern)).toHaveLength(1);
            body = body.replace(pattern, 'void GeoJSONSource;');
          }
          await route.fulfill({ response, body });
        });
        // Controlled format A/B only: both arms use the same route/current
        // renderer. The legacy arm omits the optional point-reference input.
        await page.route(url => url.pathname.endsWith('/src/map/persistentMapWorker.ts') && url.searchParams.has('worker_file'), async route => {
          const response = await route.fetch();
          let body = await response.text();
          if (legacyFormat) {
            const pattern = /, parameters\.data\?\.features\)/g;
            expect(body.match(pattern)).toHaveLength(1);
            body = body.replace(pattern, ')');
          }
          await route.fulfill({ response, body });
        });
      }
      await page.addInitScript(() => {
        (window as any).__indexEvents = [];
        const channel = new BroadcastChannel('uec-public-cluster-index-diagnostics-v1');
        channel.onmessage = event => { if (typeof event.data?.state === 'string') (window as any).__indexEvents.push(event.data); };
        (window as any).__indexChannel = channel;
        (window as any).__indexMapPhases = {};
        const timer = setInterval(() => {
          const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
          if (!map) return;
          clearInterval(timer);
          const phases = (window as any).__indexMapPhases;
          const now = () => performance.timeOrigin + performance.now();
          map.on('sourcedataloading', (event: any) => { if (event.sourceId === 'locations' && !phases.sourceLoading) phases.sourceLoading = now(); });
          map.on('sourcedata', (event: any) => { if (event.sourceId === 'locations' && event.sourceDataType === 'content' && !phases.sourceContent) phases.sourceContent = now(); });
          map.on('render', () => {
            if (phases.firstFacilitiesPaint || !map.getLayer('clusters')) return;
            if (map.queryRenderedFeatures({ layers: ['clusters'] }).length) phases.firstFacilitiesPaint = now();
          });
          map.on('idle', () => { if (phases.firstFacilitiesPaint && !phases.allIdle) phases.allIdle = now(); });
        }, 5);
      });
      await page.goto(`./#/map?release_id=${release}&lat=40&lon=-96&z=4`);
      await ready(page, 'stored', '1 / 0', true);
      // Use the actual diagnostic UI so this acceptance also exercises the
      // compiled public bundle, where development map globals do not exist.
      const loadedCount = async () => Number((await metric(page, 'Filtered / loaded mapped').innerText()).split('/')[1]!.replace(/[^0-9]/g, ''));
      const count = await loadedCount();
      const aggregate = await page.evaluate(async database => {
        const db = await new Promise<IDBDatabase>((resolve, reject) => { const request = indexedDB.open(database, 1); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); });
        try {
          const entry = await new Promise<any>((resolve, reject) => { const request = db.transaction('index').objectStore('index').get('active'); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); });
          return { bytes: entry.bytes, format: entry.snapshot.format };
        } finally { db.close(); }
      }, DATABASE);
      expect(count).toBeGreaterThan(40_000);
      expect(aggregate.bytes).toBeLessThan(64 * 1048576);
      expect(aggregate.format).toBe(legacyFormat ? 'uec-compressed-cluster-index-v1' : 'uec-referenced-cluster-index-v1');
      for (let reload = 0; reload < (profiling ? 3 : 2); reload++) {
        await page.reload();
        await ready(page, 'restored', '0 / 1', true);
        if (process.env.UEC_INDEX_PROFILE === 'true') {
          await expect.poll(() => page.evaluate(() => (window as any).__indexMapPhases.allIdle), { timeout: 15_000 }).toBeGreaterThan(0);
          const profile = await page.evaluate(() => {
            const event = (window as any).__indexEvents.find((item: any) => item.state === 'restored');
            const phases = (window as any).__indexMapPhases;
            const mark = performance.getEntriesByName('uec-public-map-feed-decoded').at(-1);
            const feedDecoded = mark ? performance.timeOrigin + mark.startTime : null;
            const resources = performance.getEntriesByType('resource') as PerformanceResourceTiming[];
            const count = (part: string) => resources.filter(resource => resource.name.includes(part)).length;
            return { worker: event?.timings, sourceToWorkerMs: phases.sourceLoading ? event?.startedAtEpochMs - phases.sourceLoading : null,
              sourceToContentMs: phases.sourceLoading && phases.sourceContent ? phases.sourceContent - phases.sourceLoading : null,
              sourceToPaintMs: phases.sourceLoading && phases.firstFacilitiesPaint ? phases.firstFacilitiesPaint - phases.sourceLoading : null,
              sourceToIdleMs: phases.sourceLoading && phases.allIdle ? phases.allIdle - phases.sourceLoading : null,
              feedDecodedToPaintMs: feedDecoded && phases.firstFacilitiesPaint ? phases.firstFacilitiesPaint - feedDecoded : null,
              navigationToPaintMs: phases.firstFacilitiesPaint ? phases.firstFacilitiesPaint - performance.timeOrigin : null,
              navigationToIdleMs: phases.allIdle ? phases.allIdle - performance.timeOrigin : null,
              requestCounts: { manifest: count('/api/v2/releases/manifest'), feed: count('/api/v2/map/feed'), worldBaseline: count('/world-baseline/') } };
          });
          console.log(JSON.stringify({ format: legacyFormat ? 'legacy-gzip' : 'point-references', transport: nativeTransport ? 'native-graph' : 'json-envelope', release, reload, indexTimingsMs: profile }));
        }
        expect(await loadedCount()).toBe(count);
        expect(await page.evaluate(() => (window as any).__indexEvents.some((event: any) => event.state === 'building'))).toBe(false);
      }
    });
  }
});
