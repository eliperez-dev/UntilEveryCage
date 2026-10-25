import { expect, test } from '@playwright/test';

async function installMapTiles(page: import('@playwright/test').Page) {
  const images = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 256;
    const context = canvas.getContext('2d')!;
    context.fillStyle = '#252b28';
    context.fillRect(0, 0, 256, 256);
    return {
      png: canvas.toDataURL('image/png').split(',')[1],
      webp: canvas.toDataURL('image/webp').split(',')[1],
    };
  });
  const png = Buffer.from(images.png, 'base64');
  const webp = Buffer.from(images.webp, 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: png }));
  await page.route('**/World_Imagery/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: png }));
  await page.route('https://tiles.mapterhorn.com/**', route => route.fulfill({ status: 200, contentType: 'image/webp', body: webp }));
}

function contrastRatio(foreground: string, background: string): number {
  const luminance = (color: string) => {
    const channels = color.match(/[\d.]+/g)?.slice(0, 3).map(Number);
    if (!channels || channels.length !== 3) throw new Error(`Unexpected computed color: ${color}`);
    const linear = channels.map(channel => {
      const value = channel / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
  };
  const first = luminance(foreground);
  const second = luminance(background);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

test('Tools map controls operate the active map and keep style values legible in both themes', async ({ page }) => {
  await installMapTiles(page);
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4');
  const map = page.getByLabel('Map showing records');
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getLayer('exact-pins')))).toBe(true);
  await expect(page.getByRole('button', { name: 'Search map' })).toBeVisible();
  await expect(map.locator('.map-controls-wrap')).toHaveCount(0);

  await page.getByRole('button', { name: 'Tools' }).click();
  const controls = page.getByRole('group', { name: 'Map view' });
  const style = controls.getByLabel('Map style');
  const camera = controls.locator('.map-camera-toggle');
  await expect(style).toBeEnabled();
  await expect(camera).toHaveText('2D');
  const themeToggle = page.locator('.masthead .theme-toggle');
  const expectStyleContrast = async (label: string) => {
    const colors = await style.evaluate(element => {
      const select = element as HTMLSelectElement;
      const computed = getComputedStyle(select);
      return { label: select.selectedOptions[0]?.textContent?.trim(), foreground: computed.color, background: computed.backgroundColor };
    });
    expect(colors.label).toBe(label);
    expect(contrastRatio(colors.foreground, colors.background)).toBeGreaterThanOrEqual(4.5);
  };
  if (await themeToggle.getAttribute('aria-pressed') !== 'true') await themeToggle.click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expectStyleContrast('Street');
  await style.selectOption('satellite');
  await expectStyleContrast('Satellite');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0])).toContain('World_Imagery');
  await themeToggle.click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expectStyleContrast('Satellite');
  await camera.click();
  await expect(camera).toHaveText('3D');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(45);
  await expect(page.getByRole('button', { name: 'Search map' })).toBeVisible();
});

for (const listState of ['closed', 'open'] as const) {
  test(`map pin selection opens its detail and centers the camera with Search ${listState}`, async ({ page }) => {
    await page.goto(`./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4&list=${listState}`);
    await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getLayer('exact-pins')))).toBe(true);
    if (listState === 'open') await expect(page.locator('#field-record-list')).toBeVisible();
    else await expect(page.getByRole('button', { name: 'Search map' })).toBeVisible();

    const mapPoint = await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const feature = {
        type: 'Feature', geometry: { type: 'Point', coordinates: [-73.9, 40.7] },
        properties: { id: 'dense-exact-0-0' }, layer: { id: 'exact-pins' },
      };
      map.jumpTo({ center: [-73.9, 40.7], zoom: 8 });
      map.queryRenderedFeatures = (_point: unknown, options: { layers?: string[] } = {}) =>
        options.layers?.includes('exact-pins') ? [feature] : [];
      return map.getCanvas().getBoundingClientRect().toJSON();
    });
    await page.mouse.click(mapPoint.x + mapPoint.width * 0.65, mapPoint.y + mapPoint.height * 0.5);
    await expect(page.locator('.dossier')).toBeVisible();
    await expect(page.locator('.dossier')).toContainText('Synthetic');
    await expect.poll(() => page.evaluate(() => {
      const center = (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getCenter();
      return center ? [Number(center.lng.toFixed(1)), Number(center.lat.toFixed(1))] : null;
    })).toEqual([-73.9, 40.7]);
  });
}

const providerReferenceKey = '0123456789abcdef0123456789abcdef';
const providerSourceId = 'de.fixture.provider-address';
const providerMember = {
  candidate_id: '123e4567-e89b-42d3-a456-426614174000',
  source_id: providerSourceId,
  location_class: 'city_postal',
  display_name: 'Fixture provider-address member',
  display_precision: 'provider_address_point_high_confidence',
  country_code: 'DE',
  city: 'Fixture locality',
  postal_code: null,
  latitude: 50.85,
  longitude: 10,
  coordinate_precision: 'provider-address',
  coordinate_method: 'geoapify_rooftop',
  coordinate_provider: 'Geoapify',
  coordinate_confidence: 0.99,
  coordinate_confidence_band: 'high',
  coordinate_review_status: 'pending_human_privacy_review',
  factual_review_status: 'not_reviewed',
  privacy_screening_status: 'pending',
  project_approval: false,
  publication_status: 'not_published',
  preview_label: 'Private real V2 candidate — not project-approved or published',
};

for (const listState of ['closed', 'open'] as const) {
  test(`weight-one provider-address reference pin uses reference members with Search ${listState}`, async ({ page }) => {
    const referenceRequests: string[] = [];
    const invalidDetailRequests: string[] = [];
    const snapshotId = 'b'.repeat(64);
    await page.route('**/v2-preview/', async route => {
      const response = await route.fetch();
      const html = (await response.text())
        .replace(/<meta name="uec-local-data-mode" content="[^"]*">/g, '')
        .replace('<head>', '<head><meta name="uec-local-data-mode" content="real-preview">');
      await route.fulfill({ response, body: html });
    });
    await page.route('**/dev/real-preview/**', async route => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      if (path === '/dev/real-preview/counts') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
          api_version: 'real-preview-v1',
          data: { facility_candidate_count: 1, numeric_coordinate_count: 1, city_postal_count: 1, map_visible_count: 1 },
          meta: { private_preview: true, snapshot_id: snapshotId },
        }) });
      }
      if (path === '/dev/real-preview/facets') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
          api_version: 'real-preview-v1', data: [{ source_id: providerSourceId, location_class: 'city_postal', count: 1 }],
        }) });
      }
      if (path === '/dev/real-preview/map/feed') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
          api_version: 'real-preview-v1',
          data: [{
            kind: 'provider_address_point_private', key: providerReferenceKey, source_id: providerSourceId,
            latitude: providerMember.latitude, longitude: providerMember.longitude, weight: 1,
            precision: 'provider_address_point_high_confidence', category_key: 'unclassified', category_keys: ['unclassified'],
          }],
          meta: { bounded: true, private_preview: true, scope: 'default_map_scope', zoom_max: 14, snapshot_id: snapshotId },
        }) });
      }
      if (path === `/dev/real-preview/map/references/${providerReferenceKey}`) {
        referenceRequests.push(route.request().url());
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
          api_version: 'real-preview-v1', data: [providerMember], meta: { private_preview: true, next_cursor: null },
        }) });
      }
      if (path.endsWith('/locations')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
          api_version: 'real-preview-v1', data: [providerMember], meta: { private_preview: true, next_cursor: null },
        }) });
      }
      if (path.startsWith('/dev/real-preview/locations/')) invalidDetailRequests.push(path);
      return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: 'not found' }) });
    });
    await page.goto(`./#/map?f1a=field&list=${listState}&lat=50.85&lon=10&z=5`);
    await expect(page.locator('[data-data-mode="real-preview"]')).toBeVisible();
    await page.waitForFunction(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return map?.isStyleLoaded() && map.isSourceLoaded('locations')
        && map.querySourceFeatures('locations').some((feature: any) => feature.properties.kind === 'provider_address_point_private');
    });
    if (listState === 'open') await expect(page.locator('#field-record-list')).toBeVisible();
    const point = await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const feature = {
        type: 'Feature', geometry: { type: 'Point', coordinates: [10, 50.85] },
        properties: { key: '0123456789abcdef0123456789abcdef', source_id: 'de.fixture.provider-address', kind: 'provider_address_point_private', precision: 'provider_address_point_high_confidence', weight: 1 },
        layer: { id: 'source-coordinate-points' },
      };
      const original = map.queryRenderedFeatures.bind(map);
      map.queryRenderedFeatures = (query: unknown, options: { layers?: string[] } = {}) =>
        options.layers?.includes('source-coordinate-points') ? [feature] : original(query, options);
      const projected = map.project([10, 50.85]);
      const bounds = map.getCanvas().getBoundingClientRect();
      return { x: bounds.left + projected.x, y: bounds.top + projected.y };
    });
    await page.mouse.click(point.x, point.y);
    await expect.poll(() => referenceRequests.length).toBeGreaterThan(0);
    await expect(page.locator('#field-record-list')).toBeVisible();
    await expect(page.locator('#field-record-list')).toContainText('Fixture provider-address member');
    expect(new URL(referenceRequests[0]!).searchParams.get('source_id')).toBe(providerSourceId);
    expect(invalidDetailRequests).toEqual([]);
    await expect(page.locator('.dossier[role="alert"]')).toHaveCount(0);
  });
}
