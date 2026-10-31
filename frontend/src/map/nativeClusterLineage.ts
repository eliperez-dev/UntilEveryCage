import type { GeoJSONSource } from 'maplibre-gl';

export type NativeLineageRequest = { parents: string[]; targets: string[] };
export type NativeLineagePair = [parent: string, child: string];
export const NATIVE_LINEAGE_PORT = 'uec-native-lineage-v1';
type Index = { tileIndex?: { stride: number; points: { id?: string | number; tags?: Record<string, unknown> }[]; trees: ({ flatData: ArrayLike<number> } | undefined)[] } };
const MAX_MARKS = 2000;

export function validNativeLineageRequest(value: unknown): value is NativeLineageRequest {
  if (!value || typeof value !== 'object') return false;
  const request = value as NativeLineageRequest;
  return [request.parents, request.targets].every(keys => Array.isArray(keys) && keys.length <= MAX_MARKS
    && keys.every(key => typeof key === 'string' && key.length <= 512));
}

/** Worker-only, version-locked read of the existing index. No descendant RPCs,
 * second index, source mutation, or private record payload crosses the worker.
 * A bottom-up pass follows parent links across any number of skipped levels.
 */
export function matchNativeClusterLineage(index: unknown, request: NativeLineageRequest): NativeLineagePair[] {
  const treeIndex = (index as Index | undefined)?.tileIndex;
  if (!treeIndex || ![6, 7].includes(treeIndex.stride) || !validNativeLineageRequest(request)) return [];
  const parents = new Set(request.parents), remaining = new Set(request.targets.filter(key => !parents.has(key)));
  const needed = new Map<string, Set<string>>([...remaining].map(key => [key, new Set([key])]));
  const pairs = new Map<string, NativeLineagePair>();
  const { stride, points, trees } = treeIndex;
  for (let zoom = trees.length - 1; zoom >= 0 && remaining.size; zoom--) {
    const data = trees[zoom]?.flatData;
    if (!data) continue;
    for (let offset = 0; offset < data.length; offset += stride) {
      const point = data[offset + 5]! > 1 ? undefined : points[data[offset + 3]!];
      const key = point ? `p:${point.tags?.key ?? point.tags?.id ?? point.tags?.facility_id ?? point.id}` : `c:${data[offset + 3]}`;
      const descendants = needed.get(key);
      if (!descendants) continue;
      const parentId = data[offset + 4]!;
      if (parentId < 0) continue;
      const parent = `c:${parentId}`;
      for (const child of descendants) {
        if (!remaining.has(child)) continue;
        if (parents.has(parent)) { pairs.set(child, [parent, child]); remaining.delete(child); }
        else {
          let next = needed.get(parent);
          if (!next) { next = new Set(); needed.set(parent, next); }
          next.add(child);
        }
      }
    }
  }
  return [...pairs.values()];
}

/** A one-use port bypasses the native actor's tile queue. The GCC fallback
 * keeps ordinary numeric child queries unchanged. Both return identity keys only.
 */
export async function readNativeClusterLineage(source: GeoJSONSource, request: NativeLineageRequest): Promise<NativeLineagePair[]> {
  if (!validNativeLineageRequest(request)) return [];
  const actor = await (source as unknown as { actorPromise: Promise<{ mapId?: string | number; target?: { postMessage(message: unknown, options: { transfer: MessagePort[] }): void }; sendAsync(message: unknown): Promise<NativeLineagePair[]> }> }).actorPromise;
  if (typeof MessageChannel !== 'undefined' && (typeof actor.mapId === 'string' || typeof actor.mapId === 'number') && actor.target?.postMessage) {
    // A dedicated reply port avoids the native actor's tile-message backlog.
    // It carries identity pairs only and is closed after this one request.
    const channel = new MessageChannel();
    const parents = new Set(request.parents), targets = new Set(request.targets);
    return new Promise((resolve, reject) => {
      const close = () => { clearTimeout(timeout); channel.port1.close(); channel.port2.close(); };
      const timeout = setTimeout(() => { close(); reject(new Error('Native lineage read timed out')); }, 500);
      channel.port1.onmessage = event => {
        const pairs = event.data;
        close();
        if (!Array.isArray(pairs) || pairs.length > MAX_MARKS || pairs.some(pair => !Array.isArray(pair) || pair.length !== 2 || !parents.has(pair[0]) || !targets.has(pair[1]))) {
          reject(new Error('Invalid native lineage reply')); return;
        }
        resolve(pairs);
      };
      try { actor.target!.postMessage({ command: NATIVE_LINEAGE_PORT, mapId: actor.mapId, request }, { transfer: [channel.port2] }); }
      catch (error) { close(); reject(error); }
    });
  }
  return actor.sendAsync({ type: 'GCC', data: { type: 'geojson', source: 'locations', uecMotionLineage: request } });
}
