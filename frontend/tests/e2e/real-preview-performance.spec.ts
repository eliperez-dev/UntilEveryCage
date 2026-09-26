import { expect, test, type Page } from '@playwright/test';

/**
 * This is a measurement harness, not a synthetic speed test. It runs only when
 * pointed at a populated, loopback-only real preview through Vite's proxy.
 * Browser code never receives a preview token and this test never makes its
 * own private API request: every measured response was initiated by the app.
 */

const enabled = Boolean(process.env.UEC_REAL_PREVIEW_URL);
const query = process.env.UEC_PERF_SEARCH_QUERY ?? 'ROMA CAPITALE';
// Use a deterministic European fallback that exercises the current Italy/France
// private-preview fixtures. Deployments with other enabled sources can provide
// their own safe map center without changing the measurement harness.
function readViewport(): { lat: number; lon: number; zoom: number } {
  const raw = process.env.UEC_PERF_VIEWPORT ?? '46.5,2.2,5';
  const [lat, lon, zoom, ...extra] = raw.split(',').map(Number);
  if (extra.length || !Number.isFinite(lat) || lat < -85 || lat > 85 ||
      !Number.isFinite(lon) || lon < -180 || lon > 180 ||
      !Number.isFinite(zoom) || zoom < 0 || zoom > 22) {
    throw new Error('UEC_PERF_VIEWPORT must be lat,lon,zoom within Web Mercator bounds.');
  }
  return { lat, lon, zoom };
}
const viewport = readViewport();
const mapRoute = (zoom = viewport.zoom, selectedId?: string) => {
  const params = new URLSearchParams({
    f1a: 'field', lat: String(viewport.lat), lon: String(viewport.lon), z: String(zoom), list: 'closed',
  });
  if (selectedId) params.set('selected', selectedId);
  return `/#/map?${params.toString()}`;
};
type InteractionSample = {
  /** Number of actual MVT HTTP responses observed during this interaction. */
  mvtResponses?: number;
  /** Response bytes from Content-Length where the server reports it. */
  mvtResponseBytes?: number | null;
  /** Sum of request-to-response-header timings observed by Playwright. */
  mvtResponseMs?: number | null;
  /** Long tasks seen on the browser main thread while the interaction settled. */
  longTaskCount?: number;
  longTaskMs?: number;
};

const budgets = {
  initialMvtReady: readBudget('UEC_PERF_BUDGET_INITIAL_MVT_MS'),
  warmPanSettle: readBudget('UEC_PERF_BUDGET_WARM_PAN_MS'),
  warmZoomSettle: readBudget('UEC_PERF_BUDGET_WARM_ZOOM_MS'),
  basemapSettle: readBudget('UEC_PERF_BUDGET_BASEMAP_MS'),
  searchResults: readBudget('UEC_PERF_BUDGET_SEARCH_MS'),
  detailSelection: readBudget('UEC_PERF_BUDGET_DETAIL_MS'),
  referenceSelection: readBudget('UEC_PERF_BUDGET_REFERENCE_MS'),
};

function readBudget(name: string): number | null {
  const raw = process.env[name];
  if (!raw) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`${name} must be a positive number of milliseconds.`);
  }
  return parsed;
}

function reportMetric(
  metrics: Record<string, { ms: number; budgetMs: number | null } & InteractionSample>,
  name: keyof typeof budgets,
  startedAt: number,
  sample: InteractionSample = {},
) {
  const ms = Math.round(performance.now() - startedAt);
  metrics[name] = { ms, budgetMs: budgets[name], ...sample };
  if (process.env.UEC_PERF_ENFORCE === '1' && budgets[name] !== null) {
    expect(ms, `${name}: ${ms}ms exceeds its ${budgets[name]}ms budget`).toBeLessThanOrEqual(budgets[name]);
  }
}

async function waitForMvtLayers(page: Page) {
  try {
    await page.waitForFunction(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      return Boolean(
        map?.isStyleLoaded?.() &&
          map?.getLayer?.('mvt-clusters') &&
          map?.getSource?.('preview-mvt'),
      );
    }, undefined, { timeout: 30_000 });
  } catch {
    throw new Error(`MVT source/layers did not initialize within 30 seconds. State: ${JSON.stringify(await readMvtReadinessState(page))}`);
  }
}

async function readMvtReadinessState(page: Page) {
  return page.evaluate(() => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    return {
      mapCreated: Boolean(map),
      styleLoaded: Boolean(map?.isStyleLoaded?.()),
      sourceExists: Boolean(map?.getSource?.('preview-mvt')),
      clusterLayerExists: Boolean(map?.getLayer?.('mvt-clusters')),
      sourceLoaded: map?.isSourceLoaded?.('preview-mvt') ?? null,
      allTilesLoaded: map?.areTilesLoaded?.() ?? null,
      moving: map?.isMoving?.() ?? null,
      zoom: map?.getZoom?.() ?? null,
      visibleDiagnosticText: document.querySelector('#map-diagnostics')?.textContent?.trim() ?? null,
      visibleErrorText: document.querySelector('.mvt-status')?.textContent?.trim() ?? null,
    };
  });
}

async function waitForVisibleMvt(page: Page) {
  // Layer/source presence is not readiness: MapLibre creates both before it
  // has received a single tile. Require its source cache to be loaded after
  // the camera stops, then wait two paint frames so a stale label-only frame
  // cannot be mistaken for a usable map.
  try {
    await page.waitForFunction(async () => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      if (!map?.isStyleLoaded?.() || map.isMoving?.() || !map.isSourceLoaded?.('preview-mvt') || !map.areTilesLoaded?.()) return false;
      await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
      return !map.isMoving?.() && map.isSourceLoaded?.('preview-mvt') && map.areTilesLoaded?.();
    }, undefined, { timeout: 30_000 });
  } catch {
    throw new Error(`MVT did not reach usable idle within 30 seconds. State: ${JSON.stringify(await readMvtReadinessState(page))}`);
  }
}

async function beginInteractionSample(page: Page) {
  await page.evaluate(() => {
    const measurements: PerformanceEntry[] = [];
    const observer = new PerformanceObserver(entries => measurements.push(...entries.getEntries()));
    observer.observe({ type: 'longtask' });
    (window as any).__UEC_PERF_LONG_TASKS__ = { measurements, observer };
  });
  const tileResponses: Array<{ durationMs: number | null; bytes: number | null }> = [];
  const requestStartedAt = new Map<unknown, number>();
  const onRequest = (request: any) => {
    if (new URL(request.url()).pathname.includes('/dev/real-preview/map/tiles/')) {
      requestStartedAt.set(request, performance.now());
    }
  };
  const onResponse = (response: any) => {
    if (!new URL(response.url()).pathname.includes('/dev/real-preview/map/tiles/')) return;
    const started = requestStartedAt.get(response.request());
    requestStartedAt.delete(response.request());
    const rawLength = response.headers()['content-length'];
    const length = rawLength ? Number(rawLength) : Number.NaN;
    tileResponses.push({
      durationMs: started === undefined ? null : Math.round(performance.now() - started),
      bytes: Number.isFinite(length) && length > 0 ? length : null,
    });
  };
  page.on('request', onRequest);
  page.on('response', onResponse);
  return async (): Promise<InteractionSample> => {
    page.off('request', onRequest);
    page.off('response', onResponse);
    return page.evaluate((responses) => {
      const state = (window as any).__UEC_PERF_LONG_TASKS__;
      state?.observer?.disconnect?.();
      const longTasks = state?.measurements ?? [];
      delete (window as any).__UEC_PERF_LONG_TASKS__;
      return {
        mvtResponses: responses.length,
        mvtResponseBytes: responses.some((response: { bytes: number | null }) => response.bytes !== null)
          ? responses.reduce((sum: number, response: { bytes: number | null }) => sum + (response.bytes ?? 0), 0)
          : null,
        mvtResponseMs: responses.some((response: { durationMs: number | null }) => response.durationMs !== null)
          ? responses.reduce((sum: number, response: { durationMs: number | null }) => sum + (response.durationMs ?? 0), 0)
          : null,
        longTaskCount: longTasks.length,
        longTaskMs: Math.round(longTasks.reduce((sum: number, entry: PerformanceEntry) => sum + entry.duration, 0)),
      };
    }, tileResponses);
  };
}

async function moveAndSettle(page: Page, change: 'pan' | 'zoom') {
  const finishSample = await beginInteractionSample(page);
  await page.evaluate(async (kind: 'pan' | 'zoom') => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    if (!map) throw new Error('The development MapLibre instance is unavailable. Run against Vite dev mode.');
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => reject(new Error(`Map ${kind} did not settle.`)), 30_000);
      map.once('moveend', () => { window.clearTimeout(timeout); resolve(); });
      if (kind === 'pan') map.panBy([160, 0], { duration: 180, essential: true });
      else map.zoomTo(map.getZoom() + 0.8, { duration: 180, essential: true });
    });
  }, change);
  await waitForVisibleMvt(page);
  return finishSample();
}

test.describe('real-preview map performance', () => {
  test.skip(!enabled, 'Requires UEC_REAL_PREVIEW_URL for a populated loopback preview.');

  test('records real map interaction timings and optionally enforces supplied budgets', async ({ page }, testInfo) => {
    test.setTimeout(180_000);
    const metrics: Record<string, { ms: number; budgetMs: number | null } & InteractionSample> = {};
    let initialListResponse: any;
    const initialList = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname.endsWith('/dev/real-preview/locations') && !url.searchParams.get('q') && response.status() === 200;
    });
    const finishInitialSample = await beginInteractionSample(page);
    const firstTile = page.waitForResponse(
      response => new URL(response.url()).pathname.includes('/dev/real-preview/map/tiles/') && response.status() === 200,
      { timeout: 30_000 },
    );

    const initialStart = performance.now();
    await page.goto(mapRoute(), { waitUntil: 'domcontentloaded' });
    initialListResponse = await initialList;
    const tileResponse = await firstTile;
    expect(tileResponse.headers()['content-type']).toContain('application/vnd.mapbox-vector-tile');
    await waitForMvtLayers(page);
    await waitForVisibleMvt(page);
    reportMetric(metrics, 'initialMvtReady', initialStart, await finishInitialSample());

    await page.getByRole('button', { name: 'Map diagnostics' }).click();
    const diagnostics = page.locator('#map-diagnostics');
    await expect(diagnostics).toContainText('Browser-visible MVT resources');
    await expect(diagnostics).toContainText('Rendered features');
    await expect(diagnostics).toContainText('Not exposed by API');
    await page.getByRole('button', { name: 'Close map diagnostics' }).click();

    const listBody = await initialListResponse.json();
    const selectedId = listBody?.data?.[0]?.candidate_id;
    expect(selectedId).toMatch(/^[0-9a-f-]{36}$/i);

    const panStart = performance.now();
    reportMetric(metrics, 'warmPanSettle', panStart, await moveAndSettle(page, 'pan'));

    const zoomStart = performance.now();
    reportMetric(metrics, 'warmZoomSettle', zoomStart, await moveAndSettle(page, 'zoom'));

    const basemapStart = performance.now();
    const finishBasemapSample = await beginInteractionSample(page);
    await page.getByRole('button', { name: 'Satellite' }).click();
    await waitForVisibleMvt(page);
    reportMetric(metrics, 'basemapSettle', basemapStart, await finishBasemapSample());

    const searchStart = performance.now();
    const searchResponse = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname.endsWith('/dev/real-preview/locations') && url.searchParams.get('q') === query && response.status() === 200;
    });
    await page.getByRole('searchbox', { name: /search across preview records/i }).fill(query);
    await searchResponse;
    await expect(page.getByRole('button', { name: /results/i })).toBeVisible();
    reportMetric(metrics, 'searchResults', searchStart);

    const detailStart = performance.now();
    const detailResponse = page.waitForResponse(response => new URL(response.url()).pathname.endsWith(`/locations/${selectedId}`) && response.status() === 200);
    await page.goto(mapRoute(Math.max(4, viewport.zoom - 1), selectedId), { waitUntil: 'domcontentloaded' });
    await detailResponse;
    await expect(page.locator('.reading-sheet.dossier')).toBeVisible();
    reportMetric(metrics, 'detailSelection', detailStart);

    // Try the configured preview center for optional reference-member timing. The
    // click is projected through MapLibre, matching the canvas interaction users use.
    await page.goto(mapRoute(Math.min(12, viewport.zoom + 5)), { waitUntil: 'domcontentloaded' });
    await waitForMvtLayers(page);
    const reference = await page.evaluate(() => {
      const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
      const item = map?.queryRenderedFeatures({ layers: ['mvt-reference-outer'] })?.[0];
      if (!item || !Array.isArray(item.geometry?.coordinates)) return null;
      const point = map.project(item.geometry.coordinates);
      return { x: point.x, y: point.y };
    });
    if (reference) {
      const referenceStart = performance.now();
      const referenceResponse = page.waitForResponse(
        response => new URL(response.url()).pathname.includes('/dev/real-preview/map/references/') && response.status() === 200,
        { timeout: 7_500 },
      ).catch(() => null);
      const canvas = page.locator('.maplibregl-canvas');
      const box = await canvas.boundingBox();
      expect(box).not.toBeNull();
      await page.mouse.click(box!.x + reference.x, box!.y + reference.y);
      // Reference members are data-dependent. Their absence must not turn a
      // map-performance run into a failed suite; record this metric only when
      // the app actually begins the optional aggregate-member request.
      if (await referenceResponse) {
        await expect(page.locator('#field-record-list ol li button').first()).toBeVisible();
        reportMetric(metrics, 'referenceSelection', referenceStart);
      }
    }

    const report = {
      measuredAt: new Date().toISOString(),
      baseUrl: new URL(testInfo.project.use.baseURL as string).origin,
      query,
      enforce: process.env.UEC_PERF_ENFORCE === '1',
      metrics,
    };
    console.info(`UEC real-preview performance: ${JSON.stringify(report)}`);
    await testInfo.attach('real-preview-map-performance.json', {
      body: JSON.stringify(report, null, 2),
      contentType: 'application/json',
    });
  });
});
