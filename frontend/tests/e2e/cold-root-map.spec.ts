import { expect, test } from '@playwright/test';
import releaseManifest from '../fixtures/release-map/manifest.json' with { type: 'json' };

const exactId = '123e4567-e89b-42d3-a456-426614174000';
const approximateId = '223e4567-e89b-42d3-a456-426614174000';
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

test('cold root and warmed reload keep map controls and exact/approximate points interactive', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'The cache-backed map lifecycle regression runs in Chromium.');

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
  let feedRequests = 0;
  const tile = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/F2sAAAAASUVORK5CYII=', 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: tile }));
  await page.route('https://server.arcgisonline.com/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: tile }));
  await page.route(url => new URL(url.href).pathname === '/api/v2/releases/manifest', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(testManifest()) }));
  await page.route(url => new URL(url.href).pathname === '/api/v2/map/feed', route => {
    feedRequests++;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(feed) });
  });
  await page.route(url => new URL(url.href).pathname === '/api/v2/locations', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ api_version: 'v2', data: listRows, meta: {
      profile: 'official', release_id: releaseId, ruleset_version: 'rules-v1',
      coverage_note: 'Synthetic browser fixture.', coverage_scope: 'Fixture only',
      count_semantics: 'Public locations', next_cursor: null, total_count: 2,
    } }),
  }));
  await page.route(url => new URL(url.href).pathname === '/api/v2/discovery/facets', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ api_version: 'v2', data: { dimensions: {} }, meta: { profile: 'official', release_id: releaseId, ruleset_version: 'rules-v1' } }),
  }));
  await page.addInitScript(() => {
    (window as any).__coldInitialHash = location.hash;
  });

  // A true direct site load starts with no hash, while App still resolves this
  // to the public map route.
  await page.goto('./');
  expect(await page.evaluate(() => (window as any).__coldInitialHash)).toBe('');
  await page.waitForFunction(() => {
    const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return current?.isStyleLoaded() && current.getSource('locations');
  });

  const search = page.getByRole('button', { name: /Search map/ });
  await expect(search).toBeVisible();
  await search.click();
  await expect(page.getByRole('searchbox').first()).toBeVisible();
  expect(new URL(page.url()).hash).toContain('list=open');
  await page.getByRole('button', { name: 'Close search panel' }).click();

  await page.getByLabel('Map style').selectOption('satellite');
  await expect.poll(() => new URL(page.url()).hash).toContain('basemap=satellite');
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getLayer('approx-reference-signal')))).toBe(true);
  await expect(page.locator('.startup-status')).toHaveCount(0);

  // Destroy and recreate the map through the real route lifecycle.
  const primary = page.getByRole('navigation', { name: 'Primary' });
  await primary.getByRole('link', { name: 'Database', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Browse records' })).toBeVisible();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Map' }).click();
  await page.waitForFunction(() => {
    const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return current?.isStyleLoaded() && current.getSource('locations');
  });

  // Reload the direct root in the same browser context: Cache Storage is now
  // warm, but the empty-hash route and its controls must still initialize.
  await page.evaluate(() => history.replaceState(history.state, '', `${location.pathname}${location.search}`));
  await page.reload();
  expect(await page.evaluate(() => (window as any).__coldInitialHash)).toBe('');
  await page.waitForFunction(() => {
    const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return current?.isStyleLoaded() && current.getSource('locations');
  });
  expect(feedRequests).toBe(1); // The second full load used the persisted public projection cache.
  await page.getByRole('button', { name: /Search map/ }).click();
  await expect(page.getByRole('searchbox').first()).toBeVisible();
  expect(new URL(page.url()).hash).toContain('list=open');
  await page.getByRole('button', { name: 'Close search panel' }).click();
  await page.getByLabel('Map style').selectOption('satellite');
  await expect.poll(() => new URL(page.url()).hash).toContain('basemap=satellite');
  await expect(page.locator('.startup-status')).toHaveCount(0);

  // Approximate records remain members of the ordinary low-zoom clusters.
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ center: [4.4, 50.9], zoom: 4 }));
  await expect.poll(() => page.evaluate(() => {
    const current = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return current.queryRenderedFeatures({ layers: ['clusters'] }).some((feature: any) =>
      feature.properties?.representedCount === 2 && feature.properties?.approximateCount === 1);
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
  await page.getByRole('button', { name: 'Close record detail' }).click();
  await expect.poll(() => new URL(page.url()).hash).not.toContain(`selected=${exactId}`);

  await moveAndCheckFeature(approximateId, approximatePoint, 'approx-reference-signal');
  await expect.poll(() => new URL(page.url()).hash).toContain(`selected=${approximateId}`);
  await expect.poll(() => page.evaluate((id) => {
    const expression = (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPaintProperty('aggregate-outer', 'circle-opacity');
    const includes = (value: unknown): boolean => value === id || (Array.isArray(value) && value.some(includes));
    return includes(expression);
  }, approximateId)).toBe(true);
  expect(feedRequests).toBe(1);
});
