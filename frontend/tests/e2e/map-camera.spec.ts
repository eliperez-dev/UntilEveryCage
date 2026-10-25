import { expect, test } from '@playwright/test';

async function installTerrainFixture(page: import('@playwright/test').Page) {
  const tileData = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 512;
    const context = canvas.getContext('2d')!;
    // Terrarium RGB 128/128/128 represents a flat elevation near zero metres.
    context.fillStyle = 'rgb(128, 128, 128)';
    context.fillRect(0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/webp').split(',')[1];
  });
  const body = Buffer.from(tileData, 'base64');
  await page.route('https://tiles.mapterhorn.com/**', route => route.fulfill({ status: 200, contentType: 'image/webp', body }));
}

test('camera tilt, map style, and URL state preserve the map view without compass controls', async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  const tileData = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 256;
    const context = canvas.getContext('2d')!;
    context.fillStyle = '#252b28';
    context.fillRect(0, 0, 256, 256);
    context.strokeStyle = '#303834';
    context.lineWidth = 1;
    for (const offset of [64, 128, 192]) {
      context.beginPath(); context.moveTo(offset, 0); context.lineTo(offset, 256); context.stroke();
      context.beginPath(); context.moveTo(0, offset); context.lineTo(256, offset); context.stroke();
    }
    return canvas.toDataURL('image/png').split(',')[1];
  });
  const pixel = Buffer.from(tileData, 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: pixel }));
  await page.route('**/World_Imagery/**', route => route.fulfill({ status: 200, contentType: 'image/png', body: pixel }));
  await installTerrainFixture(page);
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4&pitch=31&bearing=24');
  const map = page.getByLabel('Map showing records');
  const viewToggle = map.locator('.map-camera-toggle');
  await expect(map.getByRole('group', { name: 'Map view' })).toBeVisible();
  await expect(map.locator('.maplibregl-ctrl-compass')).toHaveCount(0);
  await expect(viewToggle).toHaveText('3D');
  await expect(viewToggle).toHaveAttribute('aria-pressed', 'true');
  await expect(viewToggle).toHaveAttribute('title', 'Right-drag to tilt and rotate');
  await page.screenshot({ path: testInfo.outputPath('map-controls-desktop.png') });
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(31);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getBearing())).toBe(24);
  const nav = page.getByRole('navigation', { name: 'Primary' });
  const hrefParams = new URLSearchParams((await nav.getByRole('link', { name: 'Database', exact: true }).getAttribute('href'))?.split('?')[1]);
  expect(hrefParams.get('pitch')).toBe('31');
  expect(hrefParams.get('bearing')).toBe('24');
  const mapHrefParams = new URLSearchParams((await nav.getByRole('link', { name: 'Map', exact: true }).getAttribute('href'))?.split('?')[1]);
  expect(mapHrefParams.get('pitch')).toBe('31');
  expect(mapHrefParams.get('bearing')).toBe('24');

  await viewToggle.click();
  await expect(viewToggle).toHaveText('2D');
  await expect(viewToggle).toHaveAttribute('aria-pressed', 'false');
  await expect.poll(() => new URL(page.url()).hash).not.toMatch(/pitch=/);
  await expect.poll(() => new URL(page.url()).hash).toContain('bearing=24');
  await viewToggle.click();
  await expect(viewToggle).toHaveText('3D');
  await expect(viewToggle).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => new URL(page.url()).hash).toContain('pitch=45');
  await expect.poll(() => new URL(page.url()).hash).toContain('bearing=24');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(45);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getTerrain())).toMatchObject({ source: 'mapterhorn-terrain', exaggeration: 1 });

  const mapStyle = page.getByLabel('Map style');
  await expect(mapStyle.locator('option')).toHaveText(['Street', 'Satellite']);
  await expect(mapStyle).toHaveValue('vector');
  const mapState = await page.evaluate(() => {
    const instance = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const center = instance.getCenter();
    return { lat: Number(center.lat.toFixed(5)), lon: Number(center.lng.toFixed(5)), zoom: instance.getZoom() };
  });
  await mapStyle.selectOption('satellite');
  await expect(mapStyle).toHaveValue('satellite');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0])).toContain('World_Imagery');
  await expect.poll(() => page.evaluate(() => {
    const instance = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return [instance.getPitch(), instance.getBearing(), instance.getZoom(), Boolean(instance.getLayer('clusters'))];
  })).toEqual([45, 24, mapState.zoom, true]);
  await mapStyle.selectOption('vector');
  await expect(mapStyle).toHaveValue('vector');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0])).toContain('tile.openstreetmap.org');
});

test('flat camera URLs stay compact and the camera control remains usable on touch layouts', async ({ page }, testInfo) => {
  await installTerrainFixture(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./#/map?f1a=field&scenario=dense');
  const viewToggle = page.locator('.map-camera-toggle');
  await expect(page.getByRole('group', { name: 'Map view' })).toBeVisible();
  await expect(viewToggle).toBeVisible();
  await expect(viewToggle).toHaveText('2D');
  await expect(viewToggle).toHaveAttribute('aria-pressed', 'false');
  await expect(viewToggle).toHaveAttribute('aria-describedby', 'map-camera-help');
  await page.screenshot({ path: testInfo.outputPath('map-controls-mobile.png') });
  await viewToggle.click();
  await expect(viewToggle).toHaveText('3D');
  await expect(viewToggle).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => new URL(page.url()).hash).toContain('pitch=45');
});

test('compact map view control toggles 3D and shows the map gesture hint without compass controls', async ({ page }, testInfo) => {
  await installTerrainFixture(page);
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4');
  await page.locator('.map-surface').waitFor({ state: 'visible', timeout: 30_000 });
  const controls = page.getByRole('group', { name: 'Map view' });
  const viewToggle = controls.locator('.map-camera-toggle');
  const styleSelect = controls.getByLabel('Map style');
  await expect(controls.getByText('Right-mouse to rotate / Left-mouse to pan', { exact: true })).toBeVisible();
  await expect(page.locator('.maplibregl-ctrl-compass')).toHaveCount(0);
  await expect(styleSelect.locator('option')).toHaveText(['Street', 'Satellite']);
  await expect(viewToggle).toHaveText('2D');
  await expect(controls.locator('#map-camera-help')).toHaveClass(/sr-only/);
  const rowTops = await Promise.all([
    controls.getByText('Map view', { exact: true }).boundingBox(),
    styleSelect.boundingBox(),
    viewToggle.boundingBox(),
  ]);
  expect(rowTops.every(Boolean)).toBe(true);
  const rowCenters = rowTops.map(box => box!.y + box!.height / 2);
  expect(Math.max(...rowCenters) - Math.min(...rowCenters)).toBeLessThan(2);
  await viewToggle.click();
  await expect(viewToggle).toHaveText('3D');
  await expect(viewToggle).toHaveAttribute('title', 'Right-drag to tilt and rotate');
  await page.screenshot({ path: testInfo.outputPath('map-controls-desktop.png') });
  const before = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return { pitch: map.getPitch(), bearing: map.getBearing(), tileCacheZoomLevels: map._maxTileCacheZoomLevels };
  });
  expect(before.tileCacheZoomLevels).toBe(6);
  const canvas = await page.locator('.maplibregl-canvas').boundingBox();
  expect(canvas).not.toBeNull();
  await page.mouse.move(canvas!.x + canvas!.width * 0.5, canvas!.y + canvas!.height * 0.6);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(canvas!.x + canvas!.width * 0.64, canvas!.y + canvas!.height * 0.55, { steps: 8 });
  await page.mouse.up({ button: 'right' });
  await expect.poll(() => page.evaluate((initial: { pitch: number; bearing: number }) => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return Math.abs(map.getPitch() - initial.pitch) > 1 && Math.abs(map.getBearing() - initial.bearing) > 1;
  }, before)).toBe(true);
  await expect.poll(() => new URL(page.url()).hash).toMatch(/pitch=[^&]+.*bearing=[^&]+/);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(controls).toBeVisible();
  await expect(viewToggle).toBeVisible();
  // The approved mobile toolbar puts the label above the style/toggle row
  // so Map View can share an equal-width row with Search.
  const mobileRowTops = await Promise.all([
    styleSelect.boundingBox(),
    viewToggle.boundingBox(),
  ]);
  expect(mobileRowTops.every(Boolean)).toBe(true);
  const mobileRowCenters = mobileRowTops.map(box => box!.y + box!.height / 2);
  expect(Math.max(...mobileRowCenters) - Math.min(...mobileRowCenters)).toBeLessThan(2);
  const mobileLabel = await controls.getByText('Map view', { exact: true }).boundingBox();
  expect(mobileLabel).not.toBeNull();
  expect(mobileLabel!.y + mobileLabel!.height).toBeLessThanOrEqual(mobileRowTops[0]!.y);
  await expect(controls.locator('#map-camera-help')).toHaveClass(/sr-only/);
  await expect(viewToggle).toHaveAttribute('aria-describedby', 'map-camera-help');
  await expect(controls.getByText('Right-mouse to rotate / Left-mouse to pan', { exact: true })).toBeVisible();
  await expect(page.locator('.maplibregl-ctrl-compass')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('map-controls-mobile.png') });
});

test('selecting a map pin gently centres the camera on that record', async ({ page }) => {
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4');
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getLayer('exact-pins')))).toBe(true);
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const feature = {
      type: 'Feature', geometry: { type: 'Point', coordinates: [-73.9, 40.7] },
      properties: { id: 'dense-exact-pin-centre-test' }, layer: { id: 'exact-pins' },
    };
    map.queryRenderedFeatures = () => [feature];
    map.fire('click', { point: { x: 20, y: 20 }, lngLat: { lng: -73.9, lat: 40.7 }, originalEvent: new MouseEvent('click') });
  });
  await expect.poll(() => page.evaluate(() => {
    const center = (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getCenter();
    return center ? [Number(center.lng.toFixed(1)), Number(center.lat.toFixed(1))] : null;
  })).toEqual([-73.9, 40.7]);
});

for (const dismissal of ['close button', 'Escape key', 'browser Back'] as const) {
  test(`dismissing a selected record with ${dismissal} preserves the selected camera and style`, async ({ page }) => {
    await installTerrainFixture(page);
    await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4&pitch=24&bearing=18');
    await page.locator('.map-surface').waitFor({ state: 'visible', timeout: 30_000 });
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(24);
    // Model a cold selected URL reached from a prior, wider map view. The real
    // MapLibre layer-click interaction is covered by the built-app acceptance.
    const selectedHash = '#/map?f1a=field&scenario=dense&lat=40.7&lon=-73.9&z=8&pitch=20&bearing=-17&basemap=satellite&selected=dense-exact-0-0';
    await page.goto(`./${selectedHash}`);
    await page.locator('.map-surface').waitFor({ state: 'visible', timeout: 30_000 });
    await expect(page.locator('.dossier')).toBeVisible();
    await page.evaluate(() => history.replaceState({ ...history.state, uecMapSelection: true }, '', location.href));
    await expect.poll(() => page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return [Number(map.getCenter().lng.toFixed(1)), Number(map.getCenter().lat.toFixed(1))];
    })).toEqual([-73.9, 40.7]);
    const selectedCamera = await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const center = map.getCenter();
      return { center: [Number(center.lng.toFixed(4)), Number(center.lat.toFixed(4))], zoom: Number(map.getZoom().toFixed(2)), pitch: Number(map.getPitch().toFixed(1)), bearing: Number(map.getBearing().toFixed(1)) };
    });
    if (dismissal === 'close button') await page.getByRole('button', { name: 'Close record detail' }).click();
    else if (dismissal === 'Escape key') await page.keyboard.press('Escape');
    else await page.goBack();
    await expect(page.locator('.dossier')).toBeHidden();
    await expect.poll(() => page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const center = map.getCenter();
      return { center: [Number(center.lng.toFixed(4)), Number(center.lat.toFixed(4))], zoom: Number(map.getZoom().toFixed(1)), pitch: Math.round(map.getPitch()), bearing: Number(map.getBearing().toFixed(1)) };
    })).toEqual(selectedCamera);
    const hash = new URL(page.url()).hash;
    expect(hash).toContain('basemap=satellite');
    expect(hash).not.toContain('selected=');
    expect(hash).toContain('lat=40.7');
    expect(hash).toContain('lon=-73.9');
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getStyle().sources.base.tiles[0])).toContain('World_Imagery');
  });
}

test('a directly loaded selected URL survives reload and closes without restoring an older camera', async ({ page }) => {
  await installTerrainFixture(page);
  const selectedHash = '#/map?f1a=field&scenario=dense&lat=40.7&lon=-73.9&z=8&pitch=20&bearing=-17&basemap=satellite&selected=dense-exact-0-0';
  await page.goto(`./${selectedHash}`);
  await page.locator('.map-surface').waitFor({ state: 'visible', timeout: 30_000 });
  await expect(page.locator('.dossier')).toBeVisible();
  await page.reload();
  await page.locator('.map-surface').waitFor({ state: 'visible', timeout: 30_000 });
  await expect(page.locator('.dossier')).toBeVisible();
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const center = map.getCenter();
    return [Number(center.lng.toFixed(2)), Number(center.lat.toFixed(2)), Number(map.getZoom().toFixed(1)), Math.round(map.getPitch()), Number(map.getBearing().toFixed(1))];
  })).toEqual([-73.9, 40.7, 8, 20, -17]);
  await page.getByRole('button', { name: 'Close record detail' }).click();
  await expect(page.locator('.dossier')).toBeHidden();
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const center = map.getCenter();
    return [Number(center.lng.toFixed(2)), Number(center.lat.toFixed(2)), Number(map.getZoom().toFixed(1)), Math.round(map.getPitch()), Number(map.getBearing().toFixed(1))];
  })).toEqual([-73.9, 40.7, 8, 20, -17]);
  expect(new URL(page.url()).hash).toContain('basemap=satellite');
  expect(new URL(page.url()).hash).not.toContain('selected=');
});

test('cold shared 3D URLs restore terrain after a style reload and browser Back', async ({ page }) => {
  await installTerrainFixture(page);
  await page.route(url => new URL(url.href).pathname === '/api/v2/locations', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({
      api_version: 'v2', data: [], meta: { profile: 'official', release_id: 'synthetic-camera-nav', ruleset_version: 'synthetic',
        next_cursor: null, total_count: 0, coverage_note: 'Synthetic navigation fixture.' },
    }),
  }));
  await page.route(url => new URL(url.href).pathname === '/api/v2/discovery/facets', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({
      api_version: 'v2', data: { dimensions: {} }, meta: { profile: 'official', release_id: 'synthetic-camera-nav', ruleset_version: 'synthetic' },
    }),
  }));
  await page.goto('./#/map?f1a=field&scenario=dense&lat=38&lon=-96&z=4&pitch=45&bearing=18');
  const map = page.getByLabel('Map showing records');
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getPitch())).toBe(45);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getTerrain())).toMatchObject({ source: 'mapterhorn-terrain', exaggeration: 1 });
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getSource('mapterhorn-terrain')))).toBe(true);

  await page.evaluate(async () => {
    const instance = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const current = instance.getStyle();
    const style = {
      version: 8,
      sources: { base: current.sources.base, transport: current.sources.transport },
      layers: current.layers.filter((layer: { id: string }) => layer.id === 'base' || layer.id === 'transport'),
    };
    const loaded = new Promise<void>(resolve => instance.once('style.load', resolve));
    instance.setStyle(style, { diff: false });
    await loaded;
  });
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getTerrain())).toMatchObject({ source: 'mapterhorn-terrain', exaggeration: 1 });
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getSource('mapterhorn-terrain')))).toBe(true);

  const databaseHref = await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database', exact: true }).getAttribute('href');
  const params = new URLSearchParams(databaseHref?.split('?')[1]);
  expect(params.get('pitch')).toBe('45');
  expect(params.get('bearing')).toBe('18');
  expect(params.has('f1a')).toBe(false);
  expect(params.has('scenario')).toBe(false);
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Database', exact: true }).click();
  await expect(page).toHaveURL(/#\/database\?/);
  await page.goBack();
  await expect(page).toHaveURL(/pitch=45.*bearing=18/);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.getTerrain())).toMatchObject({ source: 'mapterhorn-terrain', exaggeration: 1 });
  await expect.poll(() => page.evaluate(() => Boolean((window as any).__UEC_LOCAL_PREVIEW_MAP__?.getSource('mapterhorn-terrain')))).toBe(true);
  await expect(map).toBeVisible();
});

test('flat maps do not request elevation and a DEM failure returns to a flat map', async ({ page }) => {
  let demRequests = 0;
  await page.route('https://tiles.mapterhorn.com/**', async route => {
    demRequests++;
    await route.abort();
  });
  await page.goto('./#/map?f1a=field&scenario=dense');
  await page.waitForFunction(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return map?.isStyleLoaded() && map.getLayer('clusters');
  });
  expect(demRequests).toBe(0);
  await page.locator('.map-camera-toggle').click();
  await expect(page.getByRole('alert')).toContainText(/Terrain (tiles are unavailable|could not be loaded)/);
  await expect.poll(() => page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return { pitch: map.getPitch(), terrain: map.getTerrain(), source: map.getSource('mapterhorn-terrain') };
  })).toMatchObject({ pitch: 0, terrain: null, source: undefined });
  expect(demRequests).toBeGreaterThan(0);
});
