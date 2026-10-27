import { expect, test, type Page } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import releaseManifest from '../fixtures/release-map/manifest.json' with { type: 'json' };

test.use({ video: { mode: 'on', size: { width: 1280, height: 720 } }, viewport: { width: 1280, height: 720 } });

async function fixture(page: Page, focusedCount?: number) {
  const requests = { feeds: 0, manifests: 0 };
  const features = Array.from({ length: 3200 }, (_, i) => ({
    type: 'Feature', id: `123e4567-e89b-42d3-a456-${i.toString(16).padStart(12, '0')}`,
    geometry: { type: 'Point', coordinates: focusedCount === undefined ? [4.45 + i % 80 * .012, 50.95 + Math.floor(i / 80) * .012]
      : i < focusedCount ? [4.87 + i % 32 * .004, 51.13 + Math.floor(i / 32) * .004] : [100 + i % 80 * .012, 30 + Math.floor(i / 80) * .012] },
    properties: { facility_id: `123e4567-e89b-42d3-a456-${i.toString(16).padStart(12, '0')}`, source_id: 'fixture.source', category_key: 'slaughter', category_keys: ['slaughter'], precision: 'source_reported', weight: 1 },
  }));
  const tile = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/F2sAAAAASUVORK5CYII=', 'base64');
  await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ contentType: 'image/png', body: tile }));
  await page.route('https://server.arcgisonline.com/**', route => route.fulfill({ contentType: 'image/png', body: tile }));
  await page.route(url => url.pathname === '/api/v2/releases/manifest', route => { requests.manifests++; return route.fulfill({ json: releaseManifest }); });
  await page.route(url => url.pathname === '/api/v2/map/feed', route => { requests.feeds++; return route.fulfill({ json: {
    api_version: 'v2', data: { type: 'FeatureCollection', features }, meta: { profile: 'official', release_id: 'synthetic-release-2026-09', manifest_sha256: 'a'.repeat(64), suppression_generation: 7, feature_count: 3200, public_record_count: 3200, unmapped_count: 0, release_label: 'Synthetic animation fixture', dataset_version: 'synthetic-test' },
  } }); });
  await page.route(url => url.pathname === '/api/v2/locations', route => route.fulfill({ json: { api_version: 'v2', data: [{
    facility_id: features[0]!.id, canonical_name: 'Synthetic animation facility', country_code: 'BE', city: 'Synthetic place', category: 'slaughter',
    publication_profile: 'official', factual_review_status: 'reviewed', privacy_screening_status: 'passed', project_approval: 'approved', reviewer_role: null, publication_warning: null,
    display_precision: 'source_reported', latitude: 50.95, longitude: 4.45, first_observed_at: null, last_observed_at: null, observation_count: 1, lifecycle_status: 'active_observed',
    source_type: 'official', source_rights_status: 'cleared', provenance_source: null, provenance_source_id: 'fixture.source', provenance_source_name: 'Synthetic source',
    provenance_source_url: 'https://example.test/source', provenance_retrieved_at: '2026-01-01T00:00:00Z', release_id: 'synthetic-release-2026-09', release_ruleset_version: 'rules-v1',
  }], meta: { profile: 'official', release_id: 'synthetic-release-2026-09', ruleset_version: 'rules-v1', coverage_note: 'Synthetic animation fixture.', total_count: 3200, next_cursor: null } } }));
  await page.route(url => url.pathname === '/api/v2/discovery/facets', route => route.fulfill({ json: { api_version: 'v2', data: { dimensions: {} }, meta: { profile: 'official', release_id: 'synthetic-release-2026-09', ruleset_version: 'rules-v1' } } }));
  await page.addInitScript((profile) => {
    const native = CanvasRenderingContext2D.prototype.drawImage;
    const frames: { time: number; direction: string; x: number; y: number; image: string }[] = [];
    (window as any).__motionFrames = frames;
    (window as any).__motionPixelAlpha = [];
    let lastPixel = -Infinity;
    CanvasRenderingContext2D.prototype.drawImage = function (...args: Parameters<CanvasRenderingContext2D['drawImage']>) {
      if (this.canvas.classList.contains('native-cluster-motion')) {
        const direction = this.canvas.getAttribute('data-direction');
        if (direction) frames.push({ time: performance.now(), direction, x: Number(args[1]), y: Number(args[2]), image: (args[0] as HTMLCanvasElement).tagName });
      }
      const result = native.apply(this, args);
      if (!profile && this.canvas.classList.contains('native-cluster-motion') && this.canvas.hasAttribute('data-direction') && performance.now() - lastPixel > 20) {
        const ratio = this.canvas.width / this.canvas.clientWidth;
        const x = Math.round((Number(args[1]) + Number(args[3]) / 2) * ratio), y = Math.round((Number(args[2]) + Number(args[4]) / 2) * ratio);
        if (x >= 0 && y >= 0 && x < this.canvas.width && y < this.canvas.height) {
          (window as any).__motionPixelAlpha.push(this.getImageData(x, y, 1, 1).data[3]); lastPixel = performance.now();
        }
      }
      return result;
    };
  }, focusedCount !== undefined);
  await page.goto('./#/map?release_id=synthetic-release-2026-09&lat=51.19&lon=4.93&z=6');
  await page.waitForFunction(() => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return map?.getLayer('clusters') && map.isSourceLoaded('locations') && map.queryRenderedFeatures({ layers: ['clusters'] }).length; });
  return requests;
}

test('a slow pairing worker skips decorative motion without blocking camera movement', async ({ page }) => {
  await fixture(page);
  await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, source = map.getSource('locations');
    const moduleUrl = performance.getEntriesByType('resource').find(entry => entry.name.includes('/nativeClusterMotion.ts'))?.name;
    const { NativeClusterMotionController } = await import(moduleUrl!);
    NativeClusterMotionController.prototype.warm = function () { (window as any).__motionController = this; return Promise.resolve(); };
    map.fire('idle'); (window as any).__motionController.invalidate();
    const read = source.getClusterChildren.bind(source);
    source.getClusterChildren = async (id: number) => { await new Promise(resolve => setTimeout(resolve, 800)); return read(id); };
    map.easeTo({ zoom: 8, duration: 200 });
  });
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  await page.waitForTimeout(900);
  expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getZoom())).toBe(8);
  expect(await page.evaluate(() => (window as any).__motionFrames.length)).toBe(0);
  await expect(page.locator('.native-cluster-motion')).not.toHaveAttribute('data-direction');
});

for (const width of [1280, 390]) for (const population of [250, 500, 1000]) {
  test(`unprimed ${population} visible facilities animate on ${width}px without exceeding the canvas frame budget`, async ({ page }, testInfo) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width, height: width === 390 ? 844 : 720 });
    await fixture(page, population);
    await page.evaluate(async () => {
      const moduleUrl = performance.getEntriesByType('resource').find(entry => entry.name.includes('/nativeClusterMotion.ts'))?.name;
      const { NativeClusterMotionController } = await import(moduleUrl!);
      const findPairs = NativeClusterMotionController.prototype.findPairs;
      NativeClusterMotionController.prototype.findPairs = async function (parents: Map<string, any>, targets: Map<string, any>) {
        const pairs = await findPairs.call(this, parents, targets);
        (window as any).__motionPairing = { parents: parents.size, targets: targets.size, cached: this.children.size, parentKeys: [...parents.keys()].slice(0, 8), targetKeys: [...targets.keys()].slice(0, 8), pairs: pairs.length };
        return pairs;
      };
      const draw = NativeClusterMotionController.prototype.draw;
      const metrics: number[] = []; (window as any).__motionDrawCosts = metrics;
      NativeClusterMotionController.prototype.draw = function (...args: any[]) {
        const map = this.options.getMap();
        (window as any).__motionReadiness = { pins: map.getLayoutProperty('v1-source-pins', 'visibility'), image: map.hasImage('v1-pin-red'), limit: this.options.limit(), idle: this.options.idleDelay?.(), loaded: map.isSourceLoaded('locations') };
        const started = performance.now(), result = draw.apply(this, args);
        if (this.canvas?.hasAttribute('data-phase')) metrics.push(performance.now() - started);
        return result;
      };
      (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 10, duration: 600 });
    });
    try { await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'split').length)).toBeGreaterThan(10); }
    catch (error) { throw new Error(`Motion skipped: ${await page.locator('.native-cluster-motion').getAttribute('data-state')} ${JSON.stringify(await page.evaluate(() => ({ pairing: (window as any).__motionPairing, readiness: (window as any).__motionReadiness })))}`, { cause: error }); }
    await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
    const metrics = await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, costs = (window as any).__motionDrawCosts.sort((a: number, b: number) => a - b);
      return { samples: costs.length, p95: costs[Math.floor(costs.length * .95)], max: costs.at(-1), facilities: new Set(map.queryRenderedFeatures({ layers: ['v1-source-pins'] }).map((feature: any) => feature.properties.key)).size };
    });
    const profilePath = testInfo.outputPath('canvas-work-profile.json');
    await writeFile(profilePath, JSON.stringify({ width, population, ...metrics }));
    await testInfo.attach('canvas-work-profile', { path: profilePath, contentType: 'application/json' });
    expect(metrics.facilities).toBe(population);
    expect(metrics.samples).toBeGreaterThan(2);
    expect(metrics.p95).toBeLessThan(24);
    await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 6, duration: 600 }));
    await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'merge').length)).toBeGreaterThan(10);
    await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
    await expect.poll(() => page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const clusters = new Map(map.queryRenderedFeatures({ layers: ['clusters'] }).map((feature: any) => [feature.properties.cluster_id, Number(feature.properties.representedCount)]));
      return [...clusters.values()].reduce((sum: number, value) => sum + Number(value), 0);
    })).toBe(population);
    await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.queryRenderedFeatures({ layers: ['v1-source-pins'] }).length)).toBe(0);
    expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('clusters', 'icon-opacity'))).toBeUndefined();
    await page.screenshot({ path: testInfo.outputPath('merged-native-cluster.png') });
    // Leave the settled paint on screen long enough for the25fps review video.
    await page.waitForTimeout(150);
  });
}

test('camera idle delay controls expansion timing and dense scenes remain bounded', async ({ page }) => {
  await fixture(page, 500);
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
  await page.getByRole('button', { name: 'Close more tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  const interaction = page.locator('#map-diagnostics details').filter({ has: page.locator('#cluster-motion-idle-delay') });
  await interaction.locator('summary').click();
  await expect(page.locator('#cluster-motion-idle-delay')).toHaveValue('0');
  await page.locator('#cluster-motion-idle-delay').press('End');
  await expect(page.locator('#cluster-motion-idle-delay')).toHaveValue('500');
  await page.getByRole('button', { name: 'Close debug menu', exact: true }).click();
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, times = { ended: 0, expanded: 0 };
    (window as any).__motionDelay = times;
    map.once('zoomend', () => { times.ended = performance.now(); });
    const canvas = document.querySelector('.native-cluster-motion')!;
    const observer = new MutationObserver(() => { if (canvas.hasAttribute('data-direction')) { times.expanded = performance.now(); observer.disconnect(); } });
    observer.observe(canvas, { attributes: true, attributeFilter: ['data-direction'] });
    map.easeTo({ zoom: 10, duration: 400 });
  });
  await expect.poll(() => page.evaluate(() => (window as any).__motionDelay.expanded)).toBeGreaterThan(0);
  expect(await page.evaluate(() => { const times = (window as any).__motionDelay; return times.expanded - times.ended; })).toBeGreaterThanOrEqual(490);
  await page.waitForFunction(() => !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  await interaction.locator('summary').click();
  await page.locator('#cluster-motion-limit').press('Home');
  await page.locator('#cluster-motion-idle-delay').press('Home');
  await expect(page.locator('#cluster-motion-limit')).toHaveValue('50');
  await expect(page.locator('#cluster-motion-idle-delay')).toHaveValue('0');
  await page.getByRole('button', { name: 'Close debug menu', exact: true }).click();
  await page.evaluate(() => { (window as any).__motionFrames.length = 0; (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 6, duration: 300 }); });
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  await expect(page.locator('.native-cluster-motion')).toHaveAttribute('data-state', 'density-limit');
  expect(await page.evaluate(() => (window as any).__motionFrames.length)).toBe(0);
  await expect(page.locator('.native-cluster-motion')).not.toHaveAttribute('data-phase');
});

test('native clusters split and merge with bounded visible frames and no source reload', async ({ page }, testInfo) => {
  const requests = await fixture(page);
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, source = map.getSource('locations');
    const setData = source.setData.bind(source), setCluster = source.setClusterOptions.bind(source);
    (window as any).__motionSourceWrites = 0;
    source.setData = (...args: unknown[]) => { (window as any).__motionSourceWrites++; return setData(...args); };
    source.setClusterOptions = (...args: unknown[]) => { (window as any).__motionSourceWrites++; return setCluster(...args); };
    map.easeTo({ zoom: 8, duration: 700 });
  });
  await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'split').length)).toBeGreaterThan(10);
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  await page.waitForTimeout(250);
  const split = await page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'split') as { time: number; x: number; y: number }[]);
  expect(split.at(-1)!.time - split[0]!.time).toBeGreaterThan(100);
  expect(new Set(split.map(frame => `${frame.x.toFixed(1)}/${frame.y.toFixed(1)}`)).size).toBeGreaterThan(10);
  expect(await page.evaluate(() => (window as any).__motionPixelAlpha.filter((alpha: number) => alpha > 0).length)).toBeGreaterThan(2);
  await page.screenshot({ path: testInfo.outputPath('cluster-expanded.png') });
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 6, duration: 700 }));
  await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'merge').length)).toBeGreaterThan(10);
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  await page.waitForTimeout(250);
  const count = await page.evaluate(() => (window as any).__motionFrames.length);
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ bearing: 90, duration: 200 }));
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => (window as any).__motionFrames.length)).toBe(count);
  expect(await page.evaluate(() => (window as any).__motionSourceWrites)).toBe(0);
  expect(requests.feeds).toBe(1); expect(errors).toEqual([]);
  expect(await page.locator('.native-cluster-motion').getAttribute('data-direction')).toBeNull();
  expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('clusters', 'icon-opacity'))).toBeUndefined();
});

test('cluster clicks animate on mobile and camera interruption clears every native mask', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const requests = await fixture(page);
  const point = await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const features = map.queryRenderedFeatures({ layers: ['clusters'] });
    const feature = features.find((feature: any) => {
      const pixel = map.project(feature.geometry.coordinates); return pixel.x > 40 && pixel.x < 300 && pixel.y > 100 && pixel.y < 500;
    }) ?? features[0];
    const pixel = map.project(feature.geometry.coordinates), box = map.getCanvas().getBoundingClientRect();
    return { x: box.x + pixel.x, y: box.y + pixel.y };
  });
  await page.mouse.move(point.x, point.y);
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getCanvas().style.cursor)).toBe('pointer');
  await page.mouse.click(point.x, point.y);
  await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.length)).toBeGreaterThan(5);
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  await page.waitForTimeout(230);
  await page.screenshot({ path: testInfo.outputPath('cluster-click-mobile.png') });
  await page.evaluate(() => { (window as any).__motionFrames.length = 0; (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 6, duration: 500 }); });
  await page.waitForFunction(() => document.querySelector('.native-cluster-motion')?.getAttribute('data-direction') === 'merge');
  await page.evaluate(() => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; map.stop(); map.easeTo({ bearing: 60, duration: 150 }); });
  await expect(page.locator('.native-cluster-motion')).not.toHaveAttribute('data-direction');
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return ['clusters', 'v1-source-pins', 'approx-reference-pins'].every(layer => map.getPaintProperty(layer, 'icon-opacity') === undefined && map.getPaintProperty(layer, 'text-opacity') === undefined);
  })).toBe(true);
  expect(requests.feeds).toBe(1);
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, style = map.getStyle();
    // A fresh style, rather than copying any temporary opacity from a running
    // animation, matches ordinary style replacement with known default paint.
    for (const layer of style.layers) if (layer.source === 'locations' && layer.paint) {
      for (const property of ['icon-opacity', 'text-opacity', 'icon-opacity-transition', 'text-opacity-transition']) delete layer.paint[property];
    }
    map.setStyle(style, { diff: false });
  });
  await page.waitForFunction(() => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return map.isStyleLoaded() && map.isSourceLoaded('locations') && map.getLayer('clusters'); });
  await expect(page.locator('.native-cluster-motion')).not.toHaveAttribute('data-direction');
  expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('clusters', 'icon-opacity'))).toBeUndefined();
});

test('reduced motion and zero-duration debug controls skip the overlay and reset cleanly', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await fixture(page);
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ zoom: 8 }));
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => (window as any).__motionFrames.length)).toBe(0);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
  await page.getByRole('button', { name: 'Close more tools', exact: true }).click();
  await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
  const interaction = page.locator('#map-diagnostics details').filter({ has: page.locator('#cluster-motion-duration') });
  await interaction.locator('summary').click();
  await page.locator('#cluster-motion-duration').press('Home');
  await expect(page.locator('#cluster-motion-duration')).toHaveValue('0');
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 6, duration: 350 }));
  await page.waitForTimeout(600);
  expect(await page.evaluate(() => (window as any).__motionFrames.length)).toBe(0);
  await page.getByRole('button', { name: 'Reset temporary settings', exact: true }).click();
  await expect(page.locator('#cluster-motion-duration')).toHaveValue('210');
  await expect(page.locator('#cluster-motion-limit')).toHaveValue('1200');
});

test('one continuous zoom holds native marks then moves children once from their parent without pullbacks', async ({ page }, testInfo) => {
  await fixture(page);
  await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, canvas = document.querySelector('.native-cluster-motion')!;
    const loaded = map.isSourceLoaded.bind(map);
    let holdUntil = 0, previous: string | null = null;
    const samples = { starts: 0, frozenMs: 0, samples: 0, addedDisplacement: 0, held: 0, exposed: 0, progress: [] as number[] };
    (window as any).__zoomContinuity = samples;
    const moduleUrl = performance.getEntriesByType('resource').find(entry => entry.name.includes('/nativeClusterMotion.ts'))?.name;
    if (!moduleUrl) throw new Error('Native motion module was not loaded');
    const { NativeClusterMotionController } = await import(moduleUrl);
    const draw = NativeClusterMotionController.prototype.drawNode;
    let lastDraw = performance.now(), childKey: string | undefined;
    NativeClusterMotionController.prototype.drawNode = function (...args: any[]) {
      const [, node, from, to, progress, opacity] = args;
      lastDraw = performance.now();
      if (node.key === to.key && from.key !== to.key) {
        childKey ??= node.key;
        if (childKey === node.key) samples.progress.push(progress);
        const actual = map.project(node.coordinates), start = map.project(from.coordinates), end = map.project(to.coordinates);
        if (opacity > .1) samples.addedDisplacement = Math.max(samples.addedDisplacement, Math.hypot(start.x + (end.x - start.x) * progress - actual.x, start.y + (end.y - start.y) * progress - actual.y));
      }
      return draw.apply(this, args);
    };
    // Simulate a brief native symbol repaint pending at the visual handoff.
    // The real renderer and camera continue normally; no source data changes.
    map.isSourceLoaded = (source: string) => source === 'locations' && performance.now() < holdUntil ? false : loaded(source);
    new MutationObserver(() => {
      const direction = canvas.getAttribute('data-direction');
      if (direction && !previous) { samples.starts++; holdUntil = performance.now() + 410; }
      previous = direction;
    }).observe(canvas, { attributes: true, attributeFilter: ['data-direction'] });
    const sample = () => {
      if (canvas.hasAttribute('data-phase')) {
        samples.frozenMs = Math.max(samples.frozenMs, performance.now() - lastDraw); samples.samples++;
        if (map.isMoving()) {
          samples.held++;
          if (JSON.stringify(map.getPaintProperty('clusters', 'icon-opacity')) !== JSON.stringify(['case', ['has', 'cluster_id'], 0, 0])) samples.exposed++;
        }
      }
      if (map.isMoving() || canvas.hasAttribute('data-phase')) requestAnimationFrame(sample);
    };
    map.easeTo({ zoom: 8.8, duration: 1800 }); requestAnimationFrame(sample);
  });
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-direction'));
  const continuity = await page.evaluate(() => (window as any).__zoomContinuity as { starts: number; frozenMs: number; samples: number; addedDisplacement: number; held: number; exposed: number; progress: number[] });
  await testInfo.attach('zoom-continuity', { body: JSON.stringify(continuity), contentType: 'application/json' });
  await page.screenshot({ path: testInfo.outputPath('continuous-zoom.png') });
  // Sample coverage is not an FPS benchmark for the CI software renderer.
  // Keep multiple observations and the freeze/anchoring requirements below.
  expect(continuity.samples).toBeGreaterThan(2);
  expect(continuity.starts, JSON.stringify(continuity)).toBe(1);
  expect(continuity.frozenMs).toBeLessThan(80);
  expect(continuity.held).toBeGreaterThan(2);
  expect(continuity.exposed).toBe(0);
  expect(continuity.addedDisplacement).toBeGreaterThan(1);
  expect(continuity.progress[0]).toBeLessThan(.2);
  expect(continuity.progress.at(-1)).toBe(1);
  expect(continuity.progress.every((progress, index) => index === 0 || progress >= continuity.progress[index - 1]!)).toBe(true);
});

test('animation on and off keep the same 3D camera path and mobile wheel zoom remains monotonic', async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page);
  const elevation = Buffer.from(await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 512;
    const context = canvas.getContext('2d')!; context.fillStyle = 'rgb(128,0,0)'; context.fillRect(0, 0, 512, 512);
    return canvas.toDataURL('image/png').split(',')[1]!;
  }), 'base64');
  await page.route('https://tiles.mapterhorn.com/**', route => route.fulfill({ contentType: 'image/png', body: elevation }));
  await page.getByRole('button', { name: 'More tools', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Enable debug menu', exact: true }).check();
  await page.getByRole('button', { name: 'Close more tools', exact: true }).click();
  await page.locator('.map-navigation .dimension-button').click();
  await page.waitForFunction(() => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return map.getPitch() === 60 && map.isSourceLoaded('mapterhorn-terrain'); });
  const coarse = await page.evaluate(() => [...new Set((window as any).__UEC_LOCAL_PREVIEW_MAP__.queryRenderedFeatures({ layers: ['clusters'] }).map((feature: any) => feature.properties.cluster_id))].sort());
  const setDuration = async (duration: number) => {
    await page.getByRole('button', { name: 'Debug menu', exact: true }).click();
    const details = page.locator('#map-diagnostics details').filter({ has: page.locator('#cluster-motion-duration') });
    if (!await details.evaluate(node => (node as HTMLDetailsElement).open)) await details.locator('summary').click();
    await page.locator('#cluster-motion-duration').press('Home');
    for (let step = 0; step < duration / 10; step++) await page.locator('#cluster-motion-duration').press('ArrowRight');
    await page.getByRole('button', { name: 'Close debug menu', exact: true }).click();
  };
  const resetCamera = async () => {
    await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.jumpTo({ zoom: 6 }));
    await page.waitForFunction(expected => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const clusters = [...new Set(map.queryRenderedFeatures({ layers: ['clusters'] }).map((feature: any) => feature.properties.cluster_id))].sort();
      return !map.isMoving() && map.isSourceLoaded('locations') && JSON.stringify(clusters) === JSON.stringify(expected);
    }, coarse);
  };
  const paths: { zoom: number; lat: number; lon: number; pitch: number }[][] = [];
  for (const duration of [0, 210]) {
    await setDuration(duration); await resetCamera();
    await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, path: unknown[] = [];
      (window as any).__cameraMotionPath = path;
      const sample = () => { const center = map.getCenter(); path.push({ zoom: map.getZoom(), lat: center.lat, lon: center.lng, pitch: map.getPitch() }); };
      map.on('move', sample); map.once('moveend', () => map.off('move', sample));
      map.easeTo({ zoom: 8.8, duration: 1000 });
    });
    await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-direction'));
    paths.push(await page.evaluate(() => (window as any).__cameraMotionPath));
  }
  for (const path of paths) {
    // Software-rendered CI has a different frame rate. Require a real
    // intermediate camera position, not an arbitrary minimum FPS.
    expect(path.length).toBeGreaterThan(1);
    expect(path.some(sample => sample.zoom > 6 && sample.zoom < 8.8)).toBe(true);
    expect(path.every((sample, index) => index === 0 || sample.zoom >= path[index - 1]!.zoom - .000001)).toBe(true);
    expect(path.every(sample => sample.pitch === 60 && Math.abs(sample.lat - 51.19) < .000001 && Math.abs(sample.lon - 4.93) < .000001)).toBe(true);
    expect(path.at(-1)!.zoom).toBeCloseTo(8.8, 8);
  }
  await resetCamera();
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, zooms: number[] = [];
    (window as any).__motionFrames.length = 0;
    (window as any).__wheelCameraZooms = zooms; map.on('move', () => zooms.push(map.getZoom()));
  });
  const box = await page.evaluate(() => {
    const bounds = (window as any).__UEC_LOCAL_PREVIEW_MAP__.getCanvas().getBoundingClientRect();
    return { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height };
  });
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  for (let step = 0; step < 6; step++) { await page.mouse.wheel(0, -120); await page.waitForTimeout(40); }
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-direction'));
  const wheel = await page.evaluate(() => (window as any).__wheelCameraZooms as number[]);
  expect(wheel.length).toBeGreaterThan(1);
  expect(wheel.some(zoom => zoom > 6 && zoom < wheel.at(-1)!)).toBe(true);
  expect(wheel.every((zoom, index) => index === 0 || zoom >= wheel[index - 1]! - .000001)).toBe(true);
  expect(await page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'split').length)).toBeGreaterThan(0);
  await page.screenshot({ path: testInfo.outputPath('mobile-3d-wheel.png') });
  await testInfo.attach('camera-comparison', { body: JSON.stringify({ animationOff: paths[0], animationOn: paths[1], wheel }), contentType: 'application/json' });
});

test('a reload and repeated warm gestures keep native parent-origin movement without test priming', async ({ page }) => {
  test.setTimeout(60_000);
  await fixture(page, 500);
  for (const pass of [0, 1]) {
    if (pass) {
      await page.reload();
      await page.waitForFunction(() => { const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; return map?.getLayer('clusters') && map.isSourceLoaded('locations') && map.queryRenderedFeatures({ layers: ['clusters'] }).length; });
    }
    await page.evaluate(() => { (window as any).__motionFrames.length = 0; (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 10, duration: 500 }); });
    await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'split').length)).toBeGreaterThan(10);
    await page.waitForFunction(() => !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase') && !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
    await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 6, duration: 500 }));
    await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'merge').length)).toBeGreaterThan(10);
    await page.waitForFunction(() => !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase') && !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  }
});
