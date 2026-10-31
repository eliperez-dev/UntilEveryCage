/** Tile-local ancestry from the pinned native index. Never changes source
 * properties, the persisted index, or the public map/API payload. */
export const NATIVE_CLUSTER_PARENTS = '__uecClusterParents';
type Properties = Record<string, unknown>;
type Tile = { features: { id?: string | number; tags?: Properties | null }[] };
type Fields = { stride: number; points: { id?: string | number; tags?: Properties | null }[]; trees: ({ flatData: ArrayLike<number> } | undefined)[] };
type Index = { options?: { cluster?: boolean }; tileIndex?: Fields; getTile?: (z: number, x: number, y: number) => Tile | null };
const installed = new WeakSet<object>();
const metadata = new WeakMap<object, { parents: Map<number, number>; points: Map<string | number, number> }>();
const pointKey = (properties?: Properties | null, id?: string | number) => properties?.key ?? properties?.id ?? properties?.facility_id ?? id;

export function nativeClusterParents(properties: Properties): string[] | undefined {
  const value = properties[NATIVE_CLUSTER_PARENTS];
  if (typeof value !== 'string' || value.length > 512) return;
  if (!value) return [];
  const ids = value.split(',');
  if (ids.length > 32 || ids.some(id => !/^\d+$/.test(id) || !Number.isSafeInteger(Number(id)))) return;
  return ids.map(id => `c:${id}`);
}

/** One numeric parent-link table per existing tree generation, shared by all
 * its tiles. No spatial index, descendant queries, or per-gesture worker RPCs.
 * The root wrapper also handles native updates that replace tileIndex/trees.
 */
export function installNativeClusterMetadata<T>(value: T): T {
  if (!value || typeof value !== 'object' || installed.has(value)) return value;
  const index = value as Index, getTile = index.getTile;
  if (typeof getTile !== 'function') return value;
  installed.add(value);
  index.getTile = function (z, x, y) {
    const tile = getTile.call(this, z, x, y), fields = this.tileIndex;
    if (tile && this.options?.cluster === false) {
      for (const feature of tile.features) feature.tags = { ...feature.tags, [NATIVE_CLUSTER_PARENTS]: '' };
      return tile;
    }
    if (!tile || !fields || ![6, 7].includes(fields.stride) || !Array.isArray(fields.trees) || !Array.isArray(fields.points)) return tile;
    // Native updates rebuild the trees in place inside the same array.
    // An actual KDBush instance identifies the generation, not that array.
    const generation = fields.trees.find(tree => tree?.flatData);
    if (!generation) return tile;
    let links = metadata.get(generation);
    if (!links) {
      links = { parents: new Map(), points: new Map() };
      fields.points.forEach((point, i) => {
        const key = pointKey(point.tags, point.id);
        if (typeof key === 'string' || typeof key === 'number') links!.points.set(key, i);
      });
      // Original point offsets are below points.length; native cluster IDs
      // start above it, so both can share the same numeric parent table.
      for (const tree of fields.trees) {
        const data = tree?.flatData; if (!data) continue;
        for (let offset = 0; offset < data.length; offset += fields.stride) {
          if (data[offset + 4]! >= 0) links.parents.set(data[offset + 3]!, data[offset + 4]!);
        }
      }
      metadata.set(generation, links);
    }
    for (const feature of tile.features) {
      const key = pointKey(feature.tags, feature.id);
      let id = typeof feature.tags?.cluster_id === 'number' ? feature.tags.cluster_id
        : typeof key === 'string' || typeof key === 'number' ? links.points.get(key) : undefined;
      if (id === undefined) continue;
      const parents: number[] = [];
      for (let depth = 0; depth < 32; depth++) {
        const parent = links.parents.get(id); if (parent === undefined) break;
        parents.push(parent); id = parent;
      }
      // Point tags can be the index's original source object. Clone them so
      // this derived field cannot enter release hashes or persisted snapshots.
      feature.tags = { ...feature.tags, [NATIVE_CLUSTER_PARENTS]: parents.join(',') };
    }
    return tile;
  };
  return value;
}
