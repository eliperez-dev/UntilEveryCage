type SourceEvent = { type?: string; sourceId?: string; sourceDataType?: string };
type SourceReadinessMap = {
  getSource(id: string): unknown;
  isSourceLoaded(id: string): boolean;
  on(type: 'sourcedata' | 'error' | 'render' | 'idle', listener: (event: SourceEvent) => void): unknown;
  off(type: 'sourcedata' | 'error' | 'render' | 'idle', listener: (event: SourceEvent) => void): unknown;
};

// Raster handoffs can queue behind elevation decoding on slower devices. Keep
// the current imagery visible while allowing both stages a bounded preparation.
export const RASTER_READY_TIMEOUT_MS = 30_000;

/** Wait only for the requested source, never unrelated imagery or overlays. */
export function waitForSourceReady(map: SourceReadinessMap, sourceId: string, signal: AbortSignal, timeoutMs = 10_000, options: { requireFreshContent?: boolean } = {}): Promise<boolean> {
  if (signal.aborted) return Promise.resolve(false);
  // A changed source must publish its next metadata/content generation before
  // either a cached loaded state or a render can release the covering raster.
  let awaitingMetadata = options.requireFreshContent ?? false;
  let awaitingContent = awaitingMetadata;
  const loaded = () => !awaitingMetadata && !awaitingContent && Boolean(map.getSource(sourceId)) && map.isSourceLoaded(sourceId);
  if (loaded()) return Promise.resolve(true);
  return new Promise(resolve => {
    let settled = false;
    const finish = (ready: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout); map.off('sourcedata', onData); map.off('error', onError);
      map.off('render', onFrame); map.off('idle', onFrame);
      signal.removeEventListener('abort', onAbort); resolve(ready);
    };
    // setTiles publishes fresh metadata before its content event invalidates
    // the old tiles. That transient loaded state must not uncover the old base.
    const onData = (event: SourceEvent) => {
      if (event.sourceId !== sourceId) return;
      if (event.sourceDataType === 'metadata') {
        awaitingMetadata = false; awaitingContent = true;
        return;
      }
      if (!awaitingMetadata && (event.sourceDataType === 'content' || event.sourceDataType === undefined)) awaitingContent = false;
      if (loaded()) finish(true);
    };
    // MapLibre updates retained raster/terrain tiles during render. Removing a stale
    // pending tile can make the source ready after its final sourcedata event,
    // without another source event. Recheck this source after that native update;
    // do not wait for unrelated imagery or for global map idle.
    const onFrame = () => { if (loaded()) finish(true); };
    const onError = (event: SourceEvent) => { if (event.sourceId === sourceId) finish(false); };
    const onAbort = () => finish(false);
    const timeout = setTimeout(() => finish(false), timeoutMs);
    map.on('sourcedata', onData); map.on('error', onError); signal.addEventListener('abort', onAbort, { once: true });
    map.on('render', onFrame); map.on('idle', onFrame);
    if (signal.aborted) finish(false);
    else if (loaded()) finish(true);
  });
}

/** Terrain waits use the same source-specific lifecycle as raster handoffs. */
export const waitForTerrainSource = waitForSourceReady;
