type SourceEvent = { type?: string; sourceId?: string };
type TerrainSourceMap = {
  getSource(id: string): unknown;
  isSourceLoaded(id: string): boolean;
  on(type: 'sourcedata' | 'error', listener: (event: SourceEvent) => void): unknown;
  off(type: 'sourcedata' | 'error', listener: (event: SourceEvent) => void): unknown;
};

/** Wait only for the DEM source, never unrelated basemap or overlay requests. */
export function waitForTerrainSource(map: TerrainSourceMap, sourceId: string, signal: AbortSignal, timeoutMs = 10_000): Promise<boolean> {
  if (signal.aborted) return Promise.resolve(false);
  const loaded = () => Boolean(map.getSource(sourceId)) && map.isSourceLoaded(sourceId);
  if (loaded()) return Promise.resolve(true);
  return new Promise(resolve => {
    const finish = (ready: boolean) => {
      clearTimeout(timeout); map.off('sourcedata', onData); map.off('error', onError);
      signal.removeEventListener('abort', onAbort); resolve(ready);
    };
    const onData = (event: SourceEvent) => { if (event.sourceId === sourceId && loaded()) finish(true); };
    const onError = (event: SourceEvent) => { if (event.sourceId === sourceId) finish(false); };
    const onAbort = () => finish(false);
    const timeout = setTimeout(() => finish(false), timeoutMs);
    map.on('sourcedata', onData); map.on('error', onError); signal.addEventListener('abort', onAbort, { once: true });
    if (signal.aborted) finish(false);
    else if (loaded()) finish(true);
  });
}
