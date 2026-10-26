import KDBush from 'kdbush';

/** A deliberate compatibility boundary for GeoJSONVT 6.1.1 / KDBush 4.1.0. */
export const CLUSTER_INDEX_CODEC_VERSION = 'geojson-vt-6.1.1-kdbush-4.1.0-v1';
const MAX_POINTS = 250_000;
const MAX_BYTES = 96 * 1024 * 1024;
const MAX_PROPERTY_VALUES = 4_000_000;

type Point = {
  type: 'Point';
  id?: string | number | null;
  geometry: number[];
  tags: Record<string, unknown> | null;
  minX?: number; minY?: number; maxX?: number; maxY?: number;
};
type Tree = KDBush & { flatData: number[] };
type IndexFields = {
  options: Record<string, unknown>;
  source: Point[];
  tileIndex: {
    options: Record<string, unknown>;
    points: Point[];
    trees: (Tree | undefined)[];
    stride: number;
    clusterProps: Record<string, unknown>[];
  };
};
export type ClusterIndexSnapshot = {
  codec: typeof CLUSTER_INDEX_CODEC_VERSION;
  options: string;
  points: Point[];
  stride: number;
  clusterProps: Record<string, unknown>[];
  trees: ({ buffer: ArrayBuffer; flatData: Float64Array } | null)[];
};

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function fields(index: unknown): IndexFields | null {
  if (!object(index) || !object(index.options) || !object(index.tileIndex)) return null;
  const tileIndex = index.tileIndex;
  if (index.options.cluster !== true || !object(tileIndex.options) || !Array.isArray(tileIndex.points)
    || !Array.isArray(tileIndex.trees) || !Array.isArray(tileIndex.clusterProps)
    || ![6, 7].includes(Number(tileIndex.stride))) return null;
  // The package's private field names are confined to this version-locked codec.
  return index as unknown as IndexFields;
}

function signature(index: IndexFields): string {
  const keys = ['maxZoom', 'indexMaxZoom', 'indexMaxPoints', 'tolerance', 'extent', 'buffer',
    'lineMetrics', 'promoteId', 'generateId', 'updateable', 'cluster'];
  const clusterKeys = ['minZoom', 'maxZoom', 'minPoints', 'radius', 'extent', 'nodeSize', 'generateId'];
  return JSON.stringify([
    keys.map(key => index.options[key] ?? null),
    clusterKeys.map(key => index.tileIndex.options[key] ?? null),
    index.tileIndex.stride,
  ]);
}

function propertyValidator(budget: { bytes: number }) {
  let remaining = MAX_PROPERTY_VALUES;
  return function valid(value: unknown, depth = 0): boolean {
    budget.bytes += typeof value === 'string' ? value.length * 2 : 8;
    if (--remaining < 0 || depth > 12 || budget.bytes > MAX_BYTES) return false;
    if (value === null || typeof value === 'boolean') return true;
    if (typeof value === 'string') return value.length <= 65_536;
    if (typeof value === 'number') return Number.isFinite(value);
    if (Array.isArray(value)) {
      if (value.length > MAX_POINTS) return false;
      for (const item of value) if (!valid(item, depth + 1)) return false;
      return true;
    }
    if (!object(value) || Object.prototype.toString.call(value) !== '[object Object]') return false;
    const keys = Object.keys(value);
    if (keys.length > 64) return false;
    for (const key of keys) {
      budget.bytes += key.length * 2;
      if (budget.bytes > MAX_BYTES || key.length > 256 || key === '__proto__'
        || key === 'constructor' || key === 'prototype' || !valid(value[key], depth + 1)) return false;
    }
    return true;
  };
}

function validPoint(value: unknown, validProperties: (value: unknown) => boolean): value is Point {
  if (!object(value) || value.type !== 'Point' || !Array.isArray(value.geometry)
    || (value.geometry.length !== 2 && value.geometry.length !== 3)
    || !Number.isFinite(value.geometry[0]) || !Number.isFinite(value.geometry[1])
    || (value.geometry.length === 3 && !Number.isFinite(value.geometry[2]))
    || Math.abs(Number(value.geometry[0])) > 3 || Math.abs(Number(value.geometry[1])) > 2
    || !(value.tags === null || object(value.tags)) || !validProperties(value.tags)) return false;
  if (value.id !== undefined && value.id !== null && typeof value.id !== 'string'
    && !(typeof value.id === 'number' && Number.isFinite(value.id))) return false;
  if (typeof value.id === 'string' && value.id.length > 512) return false;
  return (value.minX === undefined || Number.isFinite(value.minX))
    && (value.minY === undefined || Number.isFinite(value.minY))
    && (value.maxX === undefined || Number.isFinite(value.maxX))
    && (value.maxY === undefined || Number.isFinite(value.maxY));
}

function validTreeOrdering(tree: Tree): boolean {
  const stack = [{ left: 0, right: tree.numItems - 1, axis: 0, minX: -Infinity, minY: -Infinity, maxX: Infinity, maxY: Infinity }];
  while (stack.length) {
    const bounds = stack.pop()!;
    const valid = (index: number) => tree.coords[index * 2]! >= bounds.minX
      && tree.coords[index * 2]! <= bounds.maxX && tree.coords[index * 2 + 1]! >= bounds.minY
      && tree.coords[index * 2 + 1]! <= bounds.maxY;
    if (bounds.right - bounds.left <= tree.nodeSize) {
      for (let index = bounds.left; index <= bounds.right; index++) if (!valid(index)) return false;
      continue;
    }
    const median = (bounds.left + bounds.right) >> 1;
    if (!valid(median)) return false;
    const coordinate = tree.coords[median * 2 + bounds.axis]!;
    const axis = 1 - bounds.axis;
    stack.push({ ...bounds, right: median - 1, axis, ...(bounds.axis ? { maxY: coordinate } : { maxX: coordinate }) });
    stack.push({ ...bounds, left: median + 1, axis, ...(bounds.axis ? { minY: coordinate } : { minX: coordinate }) });
  }
  return true;
}

/** Export only the built hierarchy; functions and reducer closures are never serialized. */
export function exportClusterIndex(index: unknown, validateNative = true, copyProperties = true): ClusterIndexSnapshot | null {
  try {
    const source = fields(index);
    if (!source || !source.tileIndex.points.length || source.tileIndex.points.length > MAX_POINTS) return null;
    const snapshot: ClusterIndexSnapshot = {
      codec: CLUSTER_INDEX_CODEC_VERSION,
      options: signature(source),
      // The worker can skip cloning only when it packs these values into an
      // immutable string synchronously, before any await or engine mutation.
      points: copyProperties ? structuredClone(source.tileIndex.points) : source.tileIndex.points,
      stride: source.tileIndex.stride,
      clusterProps: copyProperties ? structuredClone(source.tileIndex.clusterProps) : source.tileIndex.clusterProps,
      trees: Array.from(source.tileIndex.trees, tree => tree ? {
        // GeoJSONVT deliberately clears tree.data; ids still views the entire KD buffer.
        buffer: tree.ids.buffer.slice(0),
        flatData: Float64Array.from(tree.flatData),
      } : null),
    };
    return !validateNative || validate(snapshot, source) ? snapshot : null;
  } catch { return null; }
}

function validate(value: unknown, shell: IndexFields): value is ClusterIndexSnapshot {
  if (!object(value) || value.codec !== CLUSTER_INDEX_CODEC_VERSION || value.options !== signature(shell)
    || value.stride !== shell.tileIndex.stride || !Array.isArray(value.points)
    || !value.points.length || value.points.length > MAX_POINTS || !Array.isArray(value.clusterProps)
    || value.clusterProps.length > MAX_POINTS * 2 || !Array.isArray(value.trees)) return false;
  const budget = { bytes: value.points.length * 64 };
  const validProperties = propertyValidator(budget);
  if (!value.points.every(point => validPoint(point, validProperties))
    || !value.clusterProps.every(props => object(props) && validProperties(props))) return false;
  const minZoom = Number(shell.tileIndex.options.minZoom);
  const maxZoom = Number(shell.tileIndex.options.maxZoom);
  if (!Number.isInteger(minZoom) || !Number.isInteger(maxZoom) || minZoom < 0 || maxZoom > 24
    || minZoom > maxZoom || value.trees.length !== maxZoom + 2) return false;
  const trees: (Tree | null)[] = [];
  const stride = Number(value.stride);
  for (let z = 0; z < value.trees.length; z++) {
    const record: unknown = value.trees[z];
    if (z < minZoom) {
      if (record !== null) return false;
      trees.push(null); continue;
    }
    if (!object(record) || Object.prototype.toString.call(record.buffer) !== '[object ArrayBuffer]'
      || Object.prototype.toString.call(record.flatData) !== '[object Float64Array]') return false;
    const buffer = record.buffer as ArrayBuffer;
    const flatData = record.flatData as Float64Array;
    budget.bytes += buffer.byteLength + flatData.byteLength;
    if (budget.bytes > MAX_BYTES || buffer.byteLength < 8) return false;
    const tree = KDBush.from(buffer) as Tree;
    if (tree.ArrayType !== Float32Array || tree.nodeSize !== shell.tileIndex.options.nodeSize
      || tree.numItems < 1 || tree.numItems > value.points.length
      || flatData.length !== tree.numItems * stride) return false;
    const idsBytes = tree.numItems * (tree.numItems < 65536 ? 2 : 4);
    const expectedBytes = 8 + idsBytes + (8 - idsBytes % 8) % 8 + tree.numItems * 8;
    if (buffer.byteLength !== expectedBytes) return false;
    const seen = new Uint8Array(tree.numItems);
    for (let n = 0; n < tree.numItems; n++) {
      const id = tree.ids[n]!;
      if (id >= tree.numItems || seen[id]) return false;
      seen[id] = 1;
      const offset = id * stride;
      if (!Number.isFinite(tree.coords[n * 2]) || !Number.isFinite(tree.coords[n * 2 + 1])
        || tree.coords[n * 2] !== Math.fround(flatData[offset]!)
        || tree.coords[n * 2 + 1] !== Math.fround(flatData[offset + 1]!)) return false;
    }
    if (!validTreeOrdering(tree)) return false;
    // Validation only reads these values. Allocate native mutable arrays once,
    // after the whole snapshot passes, in restoreClusterIndex.
    tree.flatData = flatData as unknown as number[];
    trees.push(tree);
  }
  if (trees[maxZoom + 1]?.numItems !== value.points.length) return false;
  const pointCount = value.points.length;
  function validClusterId(id: number): boolean {
    if (!Number.isSafeInteger(id) || id < pointCount) return false;
    const encoded = id - pointCount;
    const zoom = encoded % 32;
    const origin = Math.floor(encoded / 32);
    return zoom >= minZoom + 1 && zoom <= maxZoom + 1 && origin < (trees[zoom]?.numItems ?? 0);
  }
  for (const [zoom, tree] of trees.entries()) {
    if (!tree) continue;
    for (let offset = 0; offset < tree.flatData.length; offset += stride) {
      const data = tree.flatData;
      const x = data[offset]!, y = data[offset + 1]!, processedZoom = data[offset + 2]!;
      const id = data[offset + 3]!, parent = data[offset + 4]!, count = data[offset + 5]!, property = data[offset + 6];
      if (!Number.isFinite(x) || !Number.isFinite(y) || Math.abs(x!) > 3 || Math.abs(y!) > 2
        || !(processedZoom === Infinity || (Number.isInteger(processedZoom) && processedZoom! >= minZoom && processedZoom! <= maxZoom + 1))
        || !Number.isSafeInteger(count) || count! < 1 || count! > value.points.length
        || !(parent === -1 || (validClusterId(parent!) && (parent! - pointCount) % 32 <= zoom))) return false;
      if (count === 1) {
        if (!Number.isInteger(id) || id! < 0 || id! >= value.points.length) return false;
        const point = value.points[id!] as Point;
        if (x !== Math.fround(point.geometry[0]!) || y !== Math.fround(point.geometry[1]!)) return false;
      } else if (!validClusterId(id!) || (id! - pointCount) % 32 <= zoom) return false;
      if (stride === 7 && (!Number.isSafeInteger(property) || (count === 1 ? property !== 0
        : !(property === -1 || (property! >= 0 && property! < value.clusterProps.length))))) return false;
    }
  }
  return true;
}

/**
 * Reattach a validated hierarchy to an empty native factory shell. The factory
 * supplies current reducer closures; restoration never initializes or sorts points.
 * Identity/visibility validation and public-only eligibility belong to the caller.
 */
export function restoreClusterIndex<T>(snapshot: unknown, createEmptyIndex: () => T, onTiming?: (timing: { validationMs: number; reconstructionMs: number }) => void): T | null {
  try {
    const started = performance.now();
    const instance = createEmptyIndex();
    const shell = fields(instance);
    if (!shell || shell.tileIndex.points.length !== 0 || !validate(snapshot, shell)) return null;
    const validated = performance.now();
    shell.source = snapshot.points;
    shell.tileIndex.points = snapshot.points;
    shell.tileIndex.clusterProps = snapshot.clusterProps;
    shell.tileIndex.trees = snapshot.trees.map(record => {
      if (!record) return undefined;
      const tree = KDBush.from(record.buffer) as Tree;
      const values = new Array<number>(record.flatData.length);
      for (let index = 0; index < values.length; index++) values[index] = record.flatData[index]!;
      tree.flatData = values;
      return tree;
    });
    onTiming?.({ validationMs: validated - started, reconstructionMs: performance.now() - validated });
    return instance;
  } catch { return null; }
}
