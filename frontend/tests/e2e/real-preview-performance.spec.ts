import { expect, test, type BrowserContextOptions } from '@playwright/test';

/** Measures the populated same-origin cached-MVT map; no synthetic fixtures. */
const profiles: Array<{ name: string; context: BrowserContextOptions; throttle: boolean }> = [
  { name: 'desktop', context: { viewport: { width: 1440, height: 900 } }, throttle: false },
  { name: 'mobile', context: { viewport: { width: 375, height: 812 }, deviceScaleFactor: 2, isMobile: true }, throttle: true },
];

for (const profile of profiles) {
  test(`cached MVT map performance: ${profile.name}`, async ({ browser }, testInfo) => {
    test.skip(!process.env.UEC_REAL_PREVIEW_URL, 'Requires a populated local real preview');
    test.setTimeout(240_000);
    const samples: Array<{ firstVisibleMs: number; firstTileMs: number | null; firstTileTransferredBytes: number | null;
      panMoveendMs: number; panIdleMs: number; zoomMoveendMs: number; zoomIdleMs: number;
      zoomTilesReadyAtMoveend: boolean; basemapLoadedAtMoveend: boolean; mvtTileRequests: number; firstTileRawBytes: number }> = [];

    const runs = profile.throttle ? 1 : 3;
    for (let run = 0; run < runs; run++) {
      const context = await browser.newContext(profile.context);
      const page = await context.newPage();
      let cdp;
      if (profile.throttle) {
        cdp = await context.newCDPSession(page);
        await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
        await cdp.send('Network.enable');
        await cdp.send('Network.emulateNetworkConditions', {
          offline: false, latency: 150, downloadThroughput: 200_000, uploadThroughput: 200_000,
        });
      }
      const tileRequests: string[] = [];
      page.on('request', request => {
        const path = new URL(request.url()).pathname;
        if (path.includes('/dev/real-preview/map/tiles/')) tileRequests.push(path);
      });
      const tilePending = page.waitForResponse(response =>
        new URL(response.url()).pathname.includes('/dev/real-preview/map/tiles/') && response.status() === 200,
      );
      const start = performance.now();
      await page.goto('/#/map?f1a=field&lat=41.9&lon=12.5&z=5&list=closed', { waitUntil: 'domcontentloaded' });
      const firstTile = await tilePending;
      const firstTileRawBytes = (await firstTile.body()).byteLength;
      await page.waitForFunction(() => {
        const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
        return map?.isStyleLoaded() && map.isSourceLoaded('preview-mvt') &&
          map.queryRenderedFeatures({ layers: ['mvt-clusters', 'mvt-source-coordinates', 'mvt-reference-outer'] }).length > 0;
      }, undefined, { timeout: 90_000 });
      const firstVisibleMs = Math.round(performance.now() - start);
      const tileTiming = await page.evaluate(() => {
        const entry = performance.getEntriesByType('resource').find(item => item.name.includes('/dev/real-preview/map/tiles/')) as PerformanceResourceTiming | undefined;
        return entry ? { durationMs: Math.round(entry.duration), transferredBytes: entry.transferSize || null } : null;
      });

      const interaction = async (kind: 'pan' | 'zoom') => page.evaluate(async action => {
        const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
        const started = performance.now();
        let moveendMs = 0;
        let sourceLoadedAtMoveend = false;
        let basemapLoadedAtMoveend = false;
        await new Promise<void>(resolve => {
          map.once('moveend', () => {
            moveendMs = Math.round(performance.now() - started);
            sourceLoadedAtMoveend = map.isSourceLoaded('preview-mvt');
            basemapLoadedAtMoveend = map.isSourceLoaded('base');
          });
          map.once('idle', resolve);
          if (action === 'pan') map.panBy([120, 0], { duration: 180 });
          else map.zoomTo(map.getZoom() + 0.8, { duration: 180 });
        });
        return { moveendMs, idleMs: Math.round(performance.now() - started), sourceLoadedAtMoveend, basemapLoadedAtMoveend };
      }, kind);
      const pan = await interaction('pan');
      const zoom = await interaction('zoom');
      expect(tileRequests.length).toBeGreaterThan(0);
      expect(tileRequests.every(path => /\/tiles\/\d+\/\d+\/\d+$/.test(path))).toBe(true);
      expect(tileRequests.some(path => path.includes('/map/feed'))).toBe(false);
      expect(await page.evaluate(() => (window as any).__UEC_LOCAL_PREVIEW_MAP__?.isSourceLoaded('preview-mvt'))).toBe(true);
      samples.push({ firstVisibleMs, firstTileMs: tileTiming?.durationMs ?? null,
        firstTileTransferredBytes: tileTiming?.transferredBytes ?? null,
        panMoveendMs: pan.moveendMs, panIdleMs: pan.idleMs,
        zoomMoveendMs: zoom.moveendMs, zoomIdleMs: zoom.idleMs,
        zoomTilesReadyAtMoveend: zoom.sourceLoadedAtMoveend,
        basemapLoadedAtMoveend: zoom.basemapLoadedAtMoveend,
        mvtTileRequests: tileRequests.length, firstTileRawBytes });
      await cdp?.detach();
      await context.close();
    }

    const median = (field: 'firstVisibleMs' | 'panIdleMs' | 'zoomIdleMs') => {
      const sorted = samples.map(sample => sample[field]).sort((a, b) => a - b);
      return sorted[Math.floor(sorted.length / 2)];
    };
    const report = {
      profile: profile.name,
      mobileThrottle: profile.throttle ? '4x CPU, 1.6 Mbps, 150 ms latency' : 'none',
      samples,
      medianMs: { firstVisible: median('firstVisibleMs'), pan: median('panIdleMs'), zoom: median('zoomIdleMs') },
    };
    console.info(`UEC cached MVT performance: ${JSON.stringify(report)}`);
    await testInfo.attach(`mvt-map-${profile.name}.json`, { body: JSON.stringify(report, null, 2), contentType: 'application/json' });
  });
}
