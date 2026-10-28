import type { GeoJSONSource } from 'maplibre-gl';

export type NativeLineageRequest = { parents: string[]; targets: string[] };
export type NativeLineagePair = [parent: string, child: string];
type Index = { tileIndex?: { stride: number; points: { id?: string | number; tags?: Record<string, unknown> }[]; trees: ({ flatData: ArrayLike<number> } | undefined)[] } };
const MAX_MARKS = 2000;

/** Worker-only, version-locked read of the existing index. No descendant RPCs,
 * second index, source mutation, or private record payload crosses the worker.
 * A bottom-up pass follows parent links across any number of skipped levels.
 */
export function matchNativeClusterLineage(index: unknown, request: NativeLineageRequest): NativeLineagePair[] {
  const treeIndex = (index as Index | undefined)?.tileIndex;
  if (!treeIndex || ![6, 7].includes(treeIndex.stride) || !Array.isArray(request.parents) || !Array.isArray(request.targets)
    || request.parents.length > MAX_MARKS || request.targets.length > MAX_MARKS) return [];
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

/** The pinned native worker's GCC channel keeps ordinary numeric child queries
 * unchanged. This private request returns keys only in a single round trip.
 */
export async function readNativeClusterLineage(source: GeoJSONSource, request: NativeLineageRequest): Promise<NativeLineagePair[]> {
  const actor = await (source as unknown as { actorPromise: Promise<{ sendAsync(message: unknown): Promise<NativeLineagePair[]> }> }).actorPromise;
  return actor.sendAsync({ type: 'GCC', data: { type: 'geojson', source: 'locations', uecMotionLineage: request } });
}
