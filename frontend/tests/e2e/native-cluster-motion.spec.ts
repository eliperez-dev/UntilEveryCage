import { expect, test, type Page } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import releaseManifest from '../fixtures/release-map/manifest.json' with { type: 'json' };
import { CLUSTER_MOTION_HIDDEN_STATE, clusterMotionOpacity } from '../../src/design-lab/components/nativeClusterMotion';

test.use({ video: { mode: 'on', size: { width: 1280, height: 720 } }, viewport: { width: 1280, height: 720 } });

async function fixture(page: Page, focusedCount?: number, stableNeighbor = false) {
  const requests = { feeds: 0, manifests: 0 };
  const features = Array.from({ length: 3200 }, (_, i) => ({
    type: 'Feature', id: `123e4567-e89b-42d3-a456-${i.toString(16).padStart(12, '0')}`,
    geometry: { type: 'Point', coordinates: focusedCount === undefined ? [4.45 + i % 80 * .012, 50.95 + Math.floor(i / 80) * .012]
      : i < focusedCount ? [4.87 + i % 32 * .004, 51.13 + Math.floor(i / 32) * .004]
        : stableNeighbor && i === focusedCount ? [4.5, 51.19] : [100 + i % 80 * .012, 30 + Math.floor(i / 80) * .012] },
    properties: { facility_id: `123e4567-e89b-42d3-a456-${i.toString(16).padStart(12, '0')}`, source_id: 'fixture.source', category_key: 'slaughter', category_keys: ['slaughter'], precision: 'source_reported', weight: 1 },
  }));
  const tile = Buffer.from(await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 256;
    const context = canvas.getContext('2d')!; context.fillStyle = '#eff1ef'; context.fillRect(0, 0, 256, 256);
    return canvas.toDataURL('image/png').split(',')[1]!;
  }), 'base64');
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

async function monitorMotion(page: Page) {
  await page.evaluate(async () => {
    const moduleUrl = performance.getEntriesByType('resource').find(entry => entry.name.includes('/nativeClusterMotion.ts'))?.name;
    const { NativeClusterMotionController } = await import(moduleUrl!);
    const events: unknown[] = []; (window as any).__motionLifecycle = events;
    const report = NativeClusterMotionController.prototype.report;
    NativeClusterMotionController.prototype.report = function (state: string) {
      if (events.length < 256) events.push({ time: performance.now(), state, phase: this.canvas?.getAttribute('data-phase'), direction: this.canvas?.getAttribute('data-direction'), moving: this.options.getMap()?.isMoving() });
      return report.call(this, state);
    };
    const cancel = NativeClusterMotionController.prototype.cancel;
    NativeClusterMotionController.prototype.cancel = function (...args: any[]) {
      if (events.length < 256) events.push({ time: performance.now(), cancel: args[1] ?? 'interrupted', phase: this.canvas?.getAttribute('data-phase'), moving: this.options.getMap()?.isMoving(), stack: new Error().stack?.split('\n').slice(0, 5).join('\n') });
      return cancel.apply(this, args);
    };
  });
}

test('a zoom within one cluster generation never hides or redraws unchanged native clusters', async ({ page }, testInfo) => {
  await fixture(page, 500);
  await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const original = map.queryRenderedFeatures({ layers: ['clusters'] });
    const keys = new Set(original.map((feature: any) => feature.properties.cluster_id));
    const sample = { opacities: [] as number[], redrawn: 0, unchanged: true };
    (window as any).__unchangedMotion = sample;
    const moduleUrl = performance.getEntriesByType('resource').find(entry => entry.name.includes('/nativeClusterMotion.ts'))?.name;
    const { NativeClusterMotionController } = await import(moduleUrl!);
    const draw = NativeClusterMotionController.prototype.drawNode;
    NativeClusterMotionController.prototype.drawNode = function (...args: any[]) {
      if (keys.has(args[1].properties.cluster_id) && args[5] > 0) sample.redrawn++;
      return draw.apply(this, args);
    };
    map.on('render', () => {
      if (!map.isZooming() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase')) return;
      const paint = map.style.getLayer('clusters').paint.get('icon-opacity');
      for (const feature of map.queryRenderedFeatures({ layers: ['clusters'] })) {
        if (!keys.has(feature.properties.cluster_id)) { sample.unchanged = false; continue; }
        sample.opacities.push(paint.evaluate(feature, map.getFeatureState({ source: 'locations', id: feature.id })));
      }
    });
    map.easeTo({ zoom: 6.15, duration: 400 });
  });
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
  const sample = await page.evaluate(() => (window as any).__unchangedMotion);
  await testInfo.attach('unchanged-native-visibility', { body: JSON.stringify(sample), contentType: 'application/json' });
  expect(sample.unchanged).toBe(true);
  expect(sample.opacities.length).toBeGreaterThan(2);
  expect(sample.opacities.every((opacity: number) => opacity === 1)).toBe(true);
  expect(sample.redrawn).toBe(0);
});

test('ordinary pan and rotation leave native facility pins visible and preserve their renderer', async ({ page }, testInfo) => {
  await fixture(page, 500);
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 10, duration: 500 }));
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
  await expect.poll(() => page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.queryRenderedFeatures({ layers: ['v1-source-pins'] }).length)).toBeGreaterThan(100);
  await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const sample = { frames: 0, invisible: 0, empty: 0, redrawn: 0 };
    (window as any).__movementVisibility = sample;
    const moduleUrl = performance.getEntriesByType('resource').find(entry => entry.name.includes('/nativeClusterMotion.ts'))?.name;
    const { NativeClusterMotionController } = await import(moduleUrl!);
    const draw = NativeClusterMotionController.prototype.drawNode;
    NativeClusterMotionController.prototype.drawNode = function (...args: any[]) { if (args[5] > 0) sample.redrawn++; return draw.apply(this, args); };
    map.on('render', () => {
      if (!map.isMoving()) return;
      sample.frames++;
      const features = map.queryRenderedFeatures({ layers: ['v1-source-pins'] });
      if (!features.length) sample.empty++;
      const paint = map.style.getLayer('v1-source-pins').paint.get('icon-opacity');
      for (const feature of features) if (paint.evaluate(feature, map.getFeatureState({ source: 'locations', id: feature.id })) !== 1) sample.invisible++;
    });
    const center = map.getCenter(); map.easeTo({ center: [center.lng + .002, center.lat], duration: 450 });
  });
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ bearing: 45, duration: 450 }));
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  const sample = await page.evaluate(() => (window as any).__movementVisibility);
  await testInfo.attach('pan-rotation-native-visibility', { body: JSON.stringify(sample), contentType: 'application/json' });
  expect(sample.frames).toBeGreaterThan(2);
  expect(sample.invisible).toBe(0); expect(sample.empty).toBe(0); expect(sample.redrawn).toBe(0);
});

test('a stable facility stays native while neighboring clusters split and merge', async ({ page }, testInfo) => {
  await fixture(page, 500, true);
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 8, duration: 500 }));
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
  await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const stable = map.queryRenderedFeatures({ layers: ['v1-source-pins'] }).find((feature: any) => feature.properties.facility_id.endsWith('0000000001f4'));
    if (!stable) throw new Error('Stable neighboring fixture pin was not rendered');
    const sample = { frames: 0, invisible: 0, redrawn: 0, nativeId: stable.id, sharingId: map.queryRenderedFeatures({ layers: ['v1-source-pins'] }).filter((feature: any) => feature.id === stable.id).length };
    (window as any).__stableNeighbor = sample; (window as any).__motionFrames.length = 0;
    const moduleUrl = performance.getEntriesByType('resource').find(entry => entry.name.includes('/nativeClusterMotion.ts'))?.name;
    const { NativeClusterMotionController } = await import(moduleUrl!);
    const draw = NativeClusterMotionController.prototype.drawNode;
    NativeClusterMotionController.prototype.drawNode = function (...args: any[]) {
      if (args[1].properties.facility_id === stable.properties.facility_id && args[5] > 0) sample.redrawn++;
      return draw.apply(this, args);
    };
    map.on('render', () => {
      if (!map.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase')) return;
      sample.frames++;
      if (map.style.getLayer('v1-source-pins').paint.get('icon-opacity').evaluate(stable, map.getFeatureState({ source: 'locations', id: stable.id })) !== 1) sample.invisible++;
    });
    map.easeTo({ zoom: 10, duration: 600 });
  });
  await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'split').length)).toBeGreaterThan(10);
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
  await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 8, duration: 600 }));
  await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'merge').length)).toBeGreaterThan(10);
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
  const sample = await page.evaluate(() => (window as any).__stableNeighbor);
  await testInfo.attach('stable-neighbor-native-visibility', { body: JSON.stringify(sample), contentType: 'application/json' });
  expect(sample.nativeId).toBe('123e4567-e89b-42d3-a456-0000000001f4');
  expect(sample.sharingId).toBe(1);
  expect(sample.frames).toBeGreaterThan(2); expect(sample.invisible).toBe(0); expect(sample.redrawn).toBe(0);
});

test('rapid zoom reversals retain the visible held scene and animate the final hierarchy once', async ({ page }, testInfo) => {
  await fixture(page, 500);
  await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const sample = { stage: 0, starts: [] as string[], blank: 0, frames: 0, overlay: 0, directions: [] as string[] };
    (window as any).__rapidMotion = sample;
    const moduleUrl = performance.getEntriesByType('resource').find(entry => entry.name.includes('/nativeClusterMotion.ts'))?.name;
    const { NativeClusterMotionController } = await import(moduleUrl!);
    const start = NativeClusterMotionController.prototype.onZoomStart;
    NativeClusterMotionController.prototype.onZoomStart = function (...args: any[]) {
      const result = start.apply(this, args); sample.starts.push([...this.before?.keys() ?? []].sort().join('|')); return result;
    };
    const draw = NativeClusterMotionController.prototype.draw;
    const drawNode = NativeClusterMotionController.prototype.drawNode;
    const clear = NativeClusterMotionController.prototype.clear;
    NativeClusterMotionController.prototype.clear = function (...args: any[]) { sample.overlay = 0; return clear.apply(this, args); };
    NativeClusterMotionController.prototype.draw = function (...args: any[]) { sample.overlay = 0; return draw.apply(this, args); };
    NativeClusterMotionController.prototype.drawNode = function (...args: any[]) { if (args[5] > .01) sample.overlay++; return drawNode.apply(this, args); };
    new MutationObserver(() => {
      const direction = document.querySelector('.native-cluster-motion')?.getAttribute('data-direction');
      if (direction) sample.directions.push(direction);
    }).observe(document.querySelector('.native-cluster-motion')!, { attributes: true, attributeFilter: ['data-direction'] });
    map.on('render', () => queueMicrotask(() => {
      if (!map.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase')) return;
      sample.frames++;
      const visible = map.queryRenderedFeatures({ layers: ['clusters', 'v1-source-pins'] }).some((feature: any) =>
        map.style.getLayer(feature.layer.id).paint.get('icon-opacity').evaluate(feature, map.getFeatureState({ source: 'locations', id: feature.id })) > .01);
      if (!visible && !sample.overlay) sample.blank++;
    }));
    map.on('zoom', () => {
      if (sample.stage === 0 && map.getZoom() > 7.3) {
        sample.stage = 1; queueMicrotask(() => map.easeTo({ zoom: 6.8, duration: 450 }));
      } else if (sample.stage === 1 && map.getZoom() < 7.15) {
        sample.stage = 2; queueMicrotask(() => map.easeTo({ zoom: 10, duration: 700 }));
      }
    });
    map.easeTo({ zoom: 10, duration: 1200 });
  });
  await expect.poll(() => page.evaluate(() => (window as any).__rapidMotion.stage)).toBe(2);
  await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'split').length)).toBeGreaterThan(10);
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
  const sample = await page.evaluate(() => (window as any).__rapidMotion);
  await testInfo.attach('rapid-retarget-continuity', { body: JSON.stringify(sample), contentType: 'application/json' });
  expect(sample.starts.length).toBeGreaterThanOrEqual(3);
  expect(new Set(sample.starts).size).toBe(1);
  expect(sample.frames).toBeGreaterThan(2); expect(sample.blank).toBe(0);
  expect(sample.directions).toEqual(['split']);
  await expect(page.locator('.native-cluster-motion')).toHaveAttribute('data-state', 'complete');
  expect(await page.evaluate(key => (window as any).__UEC_LOCAL_PREVIEW_MAP__.queryRenderedFeatures({ layers: ['v1-source-pins'] })
    .some((feature: any) => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getFeatureState({ source: 'locations', id: feature.id })[key]), CLUSTER_MOTION_HIDDEN_STATE)).toBe(false);
});

test('reversing during visible playback completes the moving cue without settling pins abruptly', async ({ page }, testInfo) => {
  await fixture(page, 500);
  await page.evaluate(async hiddenKey => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const sample = { reversed: false, progress: [] as number[], beforeRetargetOffset: 0, remainingSettlePixels: 0, blank: 0, frames: 0, overlay: 0, nativeChecks: 0, earlyNativeExposure: 0 };
    (window as any).__playingReversal = sample;
    const moduleUrl = performance.getEntriesByType('resource').find(entry => entry.name.includes('/nativeClusterMotion.ts'))?.name;
    const { NativeClusterMotionController } = await import(moduleUrl!);
    const draw = NativeClusterMotionController.prototype.draw, drawNode = NativeClusterMotionController.prototype.drawNode, clear = NativeClusterMotionController.prototype.clear;
    NativeClusterMotionController.prototype.draw = function (...args: any[]) { sample.overlay = 0; return draw.apply(this, args); };
    NativeClusterMotionController.prototype.clear = function (...args: any[]) { sample.overlay = 0; return clear.apply(this, args); };
    let childKey: string | undefined;
    NativeClusterMotionController.prototype.drawNode = function (...args: any[]) {
      const [, node, from, to, progress, opacity] = args;
      if (opacity > .01) sample.overlay++;
      if (this.canvas.getAttribute('data-direction') === 'split' && node.key === to.key && from.key !== to.key) {
        childKey ??= node.key;
        if (node.key === childKey) {
          sample.progress.push(progress);
          const origin = map.project(from.coordinates), destination = map.project(to.coordinates);
          sample.remainingSettlePixels = Math.hypot(destination.x - origin.x, destination.y - origin.y) * (1 - progress);
          if (!sample.reversed && progress > .15 && progress < .95) {
            sample.reversed = true; sample.beforeRetargetOffset = sample.remainingSettlePixels;
            queueMicrotask(() => map.easeTo({ zoom: 6, duration: 500 }));
          }
          if (sample.reversed && progress < 1 && map.queryRenderedFeatures({ layers: ['clusters', 'v1-source-pins'] }).some((feature: any) => feature.id === node.id)) {
            sample.nativeChecks++;
            if (map.getFeatureState({ source: 'locations', id: node.id })[hiddenKey] !== true) sample.earlyNativeExposure++;
          }
        }
      }
      return drawNode.apply(this, args);
    };
    map.on('render', () => queueMicrotask(() => {
      if (!map.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase')) return;
      sample.frames++;
      const visible = map.queryRenderedFeatures({ layers: ['clusters', 'v1-source-pins'] }).some((feature: any) =>
        map.style.getLayer(feature.layer.id).paint.get('icon-opacity').evaluate(feature, map.getFeatureState({ source: 'locations', id: feature.id })) > .01);
      if (!visible && !sample.overlay) sample.blank++;
    }));
    map.easeTo({ zoom: 10, duration: 600 });
  }, CLUSTER_MOTION_HIDDEN_STATE);
  await expect.poll(() => page.evaluate(() => (window as any).__playingReversal.reversed)).toBe(true);
  await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'merge').length)).toBeGreaterThan(10);
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
  const sample = await page.evaluate(() => (window as any).__playingReversal);
  await testInfo.attach('during-playback-retarget-continuity', { body: JSON.stringify(sample), contentType: 'application/json' });
  expect(sample.beforeRetargetOffset).toBeGreaterThan(1);
  expect(sample.progress.at(-1)).toBe(1);
  expect(sample.progress.every((progress: number, index: number) => index === 0 || progress >= sample.progress[index - 1])).toBe(true);
  expect(sample.remainingSettlePixels).toBeLessThan(.01);
  expect(sample.nativeChecks).toBeGreaterThan(0); expect(sample.earlyNativeExposure).toBe(0);
  expect(sample.frames).toBeGreaterThan(2); expect(sample.blank).toBe(0);
  expect(await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const clusters = new Map(map.queryRenderedFeatures({ layers: ['clusters'] }).map((feature: any) => [feature.id, feature.properties.representedCount]));
    return { zoom: map.getZoom(), pins: map.queryRenderedFeatures({ layers: ['v1-source-pins'] }).length, represented: [...clusters.values()].reduce((sum: number, count) => sum + Number(count), 0) };
  })).toEqual({ zoom: 6, pins: 0, represented: 500 });
  expect(await page.evaluate(key => (window as any).__UEC_LOCAL_PREVIEW_MAP__.queryRenderedFeatures({ layers: ['clusters'] })
    .some((feature: any) => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getFeatureState({ source: 'locations', id: feature.id })[key]), CLUSTER_MOTION_HIDDEN_STATE)).toBe(false);
});

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
      const renderCosts: number[] = []; (window as any).__motionNativeRenderCosts = renderCosts;
      const render = NativeClusterMotionController.prototype.onRender;
      NativeClusterMotionController.prototype.onRender = function (...args: any[]) {
        const measure = this.armed && !this.repainting, started = performance.now();
        const result = render.apply(this, args);
        if (measure) renderCosts.push(performance.now() - started);
        return result;
      };
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
      const nativeCosts = (window as any).__motionNativeRenderCosts.sort((a: number, b: number) => a - b);
      return { samples: costs.length, p95: costs[Math.floor(costs.length * .95)], max: costs.at(-1), nativeP95: nativeCosts[Math.floor(nativeCosts.length * .95)], nativeMax: nativeCosts.at(-1), facilities: new Set(map.queryRenderedFeatures({ layers: ['v1-source-pins'] }).map((feature: any) => feature.properties.key)).size };
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
    expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('clusters', 'icon-opacity'))).toEqual(clusterMotionOpacity(undefined));
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
  // Complete normal pin-artwork setup before counting gesture-driven relayouts.
  // Cold interaction remains covered by the unprimed/reload cases below.
  await page.waitForFunction(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getLayoutProperty('v1-source-pins', 'visibility') === 'visible');
  await page.evaluate(() => new Promise<void>(resolve => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__; map.once('idle', () => resolve()); map.triggerRepaint();
  }));
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, source = map.getSource('locations');
    const setData = source.setData.bind(source), setCluster = source.setClusterOptions.bind(source);
    (window as any).__motionSourceWrites = 0;
    (window as any).__motionTileRelayouts = 0;
    (window as any).__motionRelayoutReasons = [];
    const updateLayer = map.style._updateLayer.bind(map.style);
    map.style._updateLayer = (layer: any) => {
      if (layer.source === 'locations') {
        (window as any).__motionTileRelayouts++;
        (window as any).__motionRelayoutReasons.push({ layer: layer.id, stack: new Error().stack?.split('\n').slice(1, 7).join('\n') });
      }
      return updateLayer(layer);
    };
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
  await testInfo.attach('native-tile-relayout-reasons', { body: JSON.stringify(await page.evaluate(() => (window as any).__motionRelayoutReasons)), contentType: 'application/json' });
  expect(await page.evaluate(() => (window as any).__motionTileRelayouts)).toBe(0);
  expect(requests.feeds).toBe(1); expect(errors).toEqual([]);
  expect(await page.locator('.native-cluster-motion').getAttribute('data-direction')).toBeNull();
  expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('clusters', 'icon-opacity'))).toEqual(clusterMotionOpacity(undefined));
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
    return map.queryRenderedFeatures({ layers: ['clusters', 'v1-source-pins', 'approx-reference-pins'] })
      .every((feature: any) => !map.getFeatureState({ source: 'locations', id: feature.id }).__uecClusterMotionHidden);
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
  expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getPaintProperty('clusters', 'icon-opacity'))).toEqual(clusterMotionOpacity(undefined));
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
  await monitorMotion(page);
  await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, canvas = document.querySelector('.native-cluster-motion')!;
    const loaded = map.isSourceLoaded.bind(map);
    let holdUntil = 0, previous: string | null = null;
    const samples = { starts: 0, frozenMs: 0, samples: 0, addedDisplacement: 0, held: 0, exposed: 0, hasGhost: false, progress: [] as number[] };
    (window as any).__zoomContinuity = samples;
    const moduleUrl = performance.getEntriesByType('resource').find(entry => entry.name.includes('/nativeClusterMotion.ts'))?.name;
    if (!moduleUrl) throw new Error('Native motion module was not loaded');
    const { NativeClusterMotionController } = await import(moduleUrl);
    const originalKeys = new Set(map.queryRenderedFeatures({ layers: ['clusters'] }).map((feature: any) => feature.properties.cluster_id));
    const render = NativeClusterMotionController.prototype.draw;
    NativeClusterMotionController.prototype.draw = function (...args: any[]) {
      samples.hasGhost = Boolean(this.motion || this.before && [...this.before.keys()].some((key: string) => !this.present.has(key)));
      return render.apply(this, args);
    };
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
        if (samples.hasGhost) samples.frozenMs = Math.max(samples.frozenMs, performance.now() - lastDraw);
        samples.samples++;
        if (map.isMoving()) {
          samples.held++;
          const paint = map.style.getLayer('clusters').paint.get('icon-opacity');
          for (const feature of map.queryRenderedFeatures({ layers: ['clusters'] }))
            if (!originalKeys.has(feature.properties.cluster_id) && paint.evaluate(feature, map.getFeatureState({ source: 'locations', id: feature.id })) > 0) samples.exposed++;
        }
      }
      if (map.isMoving() || canvas.hasAttribute('data-phase')) requestAnimationFrame(sample);
    };
    map.easeTo({ zoom: 8.8, duration: 1800 }); requestAnimationFrame(sample);
  });
  await expect.poll(() => page.evaluate(() => (window as any).__zoomContinuity.starts)).toBe(1);
  // Camera movement ends before the holding/pairing/paint handoff phases.
  // No direction yet does not mean that the transition has completed.
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
  await expect(page.locator('.native-cluster-motion')).toHaveAttribute('data-state', 'complete');
  const continuity = await page.evaluate(() => ({ ...(window as any).__zoomContinuity, sampledPhase: document.querySelector('.native-cluster-motion')?.getAttribute('data-phase'), sampledState: document.querySelector('.native-cluster-motion')?.getAttribute('data-state') }) as { starts: number; frozenMs: number; samples: number; addedDisplacement: number; held: number; exposed: number; progress: number[] });
  await testInfo.attach('motion-completion', { body: JSON.stringify(await page.evaluate(() => ({ events: (window as any).__motionLifecycle, phase: document.querySelector('.native-cluster-motion')?.getAttribute('data-phase'), state: document.querySelector('.native-cluster-motion')?.getAttribute('data-state') }))), contentType: 'application/json' });
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
  // Two terrain camera paths and a separate real-wheel gesture journey are
  // intentionally checked together, including on software-rendered Linux.
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page);
  await monitorMotion(page);
  const elevation = Buffer.from(await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 64;
    const context = canvas.getContext('2d')!; context.fillStyle = 'rgb(128,0,0)'; context.fillRect(0, 0, 64, 64);
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
      return !map.isMoving() && map.isSourceLoaded('locations') && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase') && JSON.stringify(clusters) === JSON.stringify(expected);
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
    await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
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
  const expansionZoom = await page.evaluate(async () => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__, source = map.getSource('locations');
    const ids = [...new Set<number>(map.queryRenderedFeatures({ layers: ['clusters'] }).map((feature: any) => Number(feature.properties.cluster_id)))];
    return Math.min(...await Promise.all(ids.map(id => source.getClusterExpansionZoom(id))));
  });
  expect(Number.isFinite(expansionZoom)).toBe(true);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  // Keep rapid input/momentum coverage. Wheel delta conversion differs across
  // platforms, so a burst alone does not always reach a native expansion level.
  const burstStartZoom = await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getZoom());
  for (let step = 0; step < 6; step++) {
    await page.mouse.wheel(0, -120);
    await page.waitForTimeout(40); // Input cadence, not an animation completion wait.
  }
  await page.waitForFunction(previous => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getZoom() > previous, burstStartZoom);
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
  // Cross the next hierarchy gradually. Large fallback deltas can skip a
  // parent/child generation before the software renderer places its symbols.
  for (let step = 6; step < 24; step++) {
    if (await page.evaluate(() => (window as any).__motionFrames.some((frame: any) => frame.direction === 'split'))) break;
    expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getZoom()), `No split after the native expansion zoom ${expansionZoom}`).toBeLessThan(expansionZoom + 1);
    const previousZoom = await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getZoom());
    await page.mouse.wheel(0, -120);
    await page.waitForFunction(previous => (window as any).__UEC_LOCAL_PREVIEW_MAP__.getZoom() > previous, previousZoom);
    await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
    if (await page.evaluate(() => (window as any).__motionFrames.some((frame: any) => frame.direction === 'split'))) break;
  }
  await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'split').length)).toBeGreaterThan(0);
  await page.waitForFunction(() => !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving() && !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase'));
  await expect(page.locator('.native-cluster-motion')).toHaveAttribute('data-state', 'complete');
  const wheel = await page.evaluate(() => (window as any).__wheelCameraZooms as number[]);
  await testInfo.attach('wheel-completion', { body: JSON.stringify(await page.evaluate(() => ({ events: (window as any).__motionLifecycle, phase: document.querySelector('.native-cluster-motion')?.getAttribute('data-phase'), state: document.querySelector('.native-cluster-motion')?.getAttribute('data-state') }))), contentType: 'application/json' });
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
    // A source can expose its first cluster before initial style/tile placement
    // settles. Start from a genuinely idle map, without priming its hierarchy.
    await page.evaluate(() => new Promise<void>(resolve => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const ready = () => {
        if (!map.loaded() || map.isMoving() || !map.isSourceLoaded('locations') || !map.queryRenderedFeatures({ layers: ['clusters'] }).length) return;
        map.off('idle', ready); resolve();
      };
      map.on('idle', ready);
      // Request one render so an already idle map also emits the readiness cue.
      map.triggerRepaint();
    }));
    await page.evaluate(() => { (window as any).__motionFrames.length = 0; (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 10, duration: 500 }); });
    await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'split').length)).toBeGreaterThan(10);
    await page.waitForFunction(() => !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase') && !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
    await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__.easeTo({ zoom: 6, duration: 500 }));
    await expect.poll(() => page.evaluate(() => (window as any).__motionFrames.filter((frame: any) => frame.direction === 'merge').length)).toBeGreaterThan(10);
    await page.waitForFunction(() => !document.querySelector('.native-cluster-motion')?.hasAttribute('data-phase') && !(window as any).__UEC_LOCAL_PREVIEW_MAP__.isMoving());
  }
});
