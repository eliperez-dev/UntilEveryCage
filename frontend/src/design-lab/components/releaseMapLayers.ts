/** Release-scoped public MVT layers. Features are already privacy-filtered and
 * clustered by the server; the browser never receives a facility feed. */

export const RELEASE_MAP_SOURCE_LAYER = 'uec_map';

/** The only properties the public map projection may expose. */
export const RELEASE_MAP_PROPERTIES = [
  'feature_key', 'kind', 'count', 'exact_count', 'coarse_count',
  'next_zoom', 'record_id', 'category_key', 'category_keys_compact',
] as const;
export const RELEASE_MAP_CATEGORY_KEYS = [
  'animal_keeping_and_production', 'slaughter', 'processing_and_preparation',
  'research_and_animal_use', 'other_regulated_premises', 'unclassified',
] as const;

export type ReleaseMapOptions = Readonly<{
  tileTemplate: string;
  minZoom?: number;
  maxZoom?: number;
  opacity?: number;
}>;

type MapLike = {
  addSource(id: string, source: unknown): void;
  addLayer(layer: unknown): void;
  getLayer(id: string): unknown;
  getSource(id: string): unknown;
  removeLayer(id: string): void;
  removeSource(id: string): void;
  setFilter?(id: string, filter: unknown): void;
};

const exactKindFilter = ['==', ['get', 'kind'], 'exact'];
const LEGACY_KEY_ALIASES: Readonly<Record<string, readonly string[]>> = Object.freeze({
  animal_keeping_and_production: ['animal_production', 'farm'],
  processing_and_preparation: ['processing'],
  research_and_animal_use: ['research', 'laboratory'],
  other_regulated_premises: ['other_regulated', 'dealer', 'exhibitor'],
});

/** Stable delimiter-bounded encoding used by MVT, which cannot carry arrays. */
export function compactCategoryKeys(keys: readonly string[]): string {
  const canonical = [...new Set(keys.filter((key): key is (typeof RELEASE_MAP_CATEGORY_KEYS)[number] =>
    (RELEASE_MAP_CATEGORY_KEYS as readonly string[]).includes(key)))].sort(
      (a, b) => RELEASE_MAP_CATEGORY_KEYS.indexOf(a) - RELEASE_MAP_CATEGORY_KEYS.indexOf(b),
    );
  return canonical.length ? `|${canonical.join('|')}|` : '|unclassified|';
}

export function compactCategoryKeysMatch(compact: string | null | undefined, selected: readonly string[], scalar?: string | null): boolean {
  if (compact !== undefined && compact !== null) return selected.some(key => compact.includes(`|${key}|`));
  return selected.some(key => [key, ...(LEGACY_KEY_ALIASES[key] ?? [])].includes(scalar ?? ''));
}

/** Changes only the already-loaded exact feature layer; server clusters stay neutral. */
export function setReleaseMapCategoryFilter(map: MapLike, namespace: string, selected: readonly string[]): boolean {
  const layerId = `${ids(namespace).layers[5]}`;
  if (!map.getLayer(layerId) || !map.setFilter) return false;
  const tokens = [...new Set(selected.map(key => `|${key}|`))];
  const scalarKeys = [...new Set(selected.flatMap(key => [key, ...(LEGACY_KEY_ALIASES[key] ?? [])]))];
  map.setFilter(layerId, tokens.length
    ? ['all', exactKindFilter, ['case', ['has', 'category_keys_compact'],
      ['any', ...tokens.map(token => ['in', token, ['get', 'category_keys_compact']])],
      ['in', ['get', 'category_key'], ['literal', scalarKeys]]]]
    : exactKindFilter);
  return true;
}

function ids(namespace: string) {
  if (!/^[A-Za-z0-9_-]+$/.test(namespace)) {
    throw new Error('Release map namespace must contain only letters, numbers, _ or -.');
  }
  const prefix = `release-${namespace}`;
  return {
    source: `${prefix}-source`,
    layers: [
      `${prefix}-cluster-circle`, `${prefix}-cluster-count`, `${prefix}-coarse-area`, `${prefix}-coarse-count`,
      `${prefix}-coarse-label`, `${prefix}-exact-pin`,
    ],
  };
}

/** Add one uniquely namespaced release source and its visual layers. */
export function addReleaseMapLayers(
  map: MapLike,
  namespace: string,
  options: ReleaseMapOptions,
): Readonly<{ sourceId: string; layerIds: readonly string[] }> {
  const { source, layers } = ids(namespace);
  if (map.getSource(source) || layers.some((id) => map.getLayer(id))) {
    throw new Error(`Release map namespace "${namespace}" is already attached.`);
  }
  const minzoom = options.minZoom ?? 0;
  const maxzoom = options.maxZoom ?? 14;
  const opacity = options.opacity ?? 1;
  if (!Number.isFinite(minzoom) || !Number.isFinite(maxzoom) || minzoom < 0 || maxzoom < minzoom) {
    throw new Error('Release map zoom range is invalid.');
  }
  if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1) {
    throw new Error('Release map opacity must be between 0 and 1.');
  }

  map.addSource(source, {
    type: 'vector',
    tiles: [options.tileTemplate],
    minzoom,
    maxzoom,
  });

  const sourceLayer = RELEASE_MAP_SOURCE_LAYER;
  const kind = (value: string) => ['==', ['get', 'kind'], value];
  const count = ['coalesce', ['get', 'count'], 1];
  const exactCount = ['coalesce', ['get', 'exact_count'], 0];
  const coarseCount = ['coalesce', ['get', 'coarse_count'], 0];
  const composition = ['concat', 'E ', ['to-string', exactCount], ' · C ', ['to-string', coarseCount]];

  map.addLayer({
    id: layers[0], type: 'circle', source, 'source-layer': sourceLayer,
    filter: kind('cluster'),
    paint: {
      'circle-radius': ['step', count, 13, 10, 17, 100, 22],
      'circle-color': ['case', ['>', coarseCount, 0], ['case', ['>', exactCount, 0], '#b89c70', '#98784b'], '#c3b17b'],
      'circle-opacity': 0.92 * opacity,
      'circle-stroke-color': '#171a18', 'circle-stroke-width': 2,
      'circle-stroke-opacity': opacity,
    },
  });
  map.addLayer({
    id: layers[1], type: 'symbol', source, 'source-layer': sourceLayer,
    filter: kind('cluster'),
    layout: {
      'text-field': ['concat', ['to-string', count], '\n', composition],
      'text-font': ['Open Sans Bold'], 'text-size': 10,
      'text-allow-overlap': true, 'text-ignore-placement': true,
    },
    paint: { 'text-color': '#172019', 'text-opacity': opacity },
  });
  map.addLayer({
    id: layers[2], type: 'circle', source, 'source-layer': sourceLayer,
    filter: kind('coarse'),
    paint: {
      'circle-color': '#292117', 'circle-radius': 17, 'circle-opacity': 0.28 * opacity,
      'circle-stroke-color': '#c9a36e', 'circle-stroke-width': 2,
      'circle-stroke-opacity': opacity,
    },
  });
  map.addLayer({
    id: layers[3], type: 'symbol', source, 'source-layer': sourceLayer,
    filter: kind('coarse'),
    layout: { 'text-field': ['to-string', count], 'text-font': ['Open Sans Bold'], 'text-size': 12 },
    paint: { 'text-color': '#f1efe8', 'text-opacity': opacity },
  });
  map.addLayer({
    id: layers[4], type: 'symbol', source, 'source-layer': sourceLayer,
    filter: kind('coarse'),
    layout: {
      'text-field': 'APPROX.', 'text-font': ['Open Sans Bold'], 'text-size': 9,
      'text-offset': [0, 2.6], 'text-allow-overlap': true, 'text-ignore-placement': true,
    },
    paint: { 'text-color': '#c9a36e', 'text-halo-color': '#171a18', 'text-halo-width': 1.5, 'text-opacity': opacity },
  });
  map.addLayer({
    id: layers[5], type: 'symbol', source, 'source-layer': sourceLayer,
    filter: kind('exact'),
    layout: {
      'text-field': ['match', ['get', 'category_key'],
        'animal_keeping_and_production', '●', 'animal_production', '●', 'farm', '●',
        'slaughter', '◆',
        'processing_and_preparation', '■', 'processing', '■',
        'research_and_animal_use', '⬢', 'research', '⬢', 'laboratory', '⬢',
        'other_regulated_premises', '▲', 'other_regulated', '▲', 'dealer', '▲', 'exhibitor', '▲', '○'],
      'text-font': ['Open Sans Bold'], 'text-size': 17,
      'text-allow-overlap': true, 'text-ignore-placement': true,
    },
    paint: {
      'text-color': ['match', ['get', 'category_key'],
        'animal_keeping_and_production', '#009E73', 'animal_production', '#009E73', 'farm', '#009E73',
        'slaughter', '#D55E00',
        'processing_and_preparation', '#0072B2', 'processing', '#0072B2',
        'research_and_animal_use', '#CC79A7', 'research', '#CC79A7', 'laboratory', '#CC79A7',
        'other_regulated_premises', '#E69F00', 'other_regulated', '#E69F00', 'dealer', '#E69F00', 'exhibitor', '#E69F00', '#B8B8B8'],
      'text-halo-color': '#171a18', 'text-halo-width': 1.5,
      'text-opacity': 0.98 * opacity,
    },
  });

  return Object.freeze({ sourceId: source, layerIds: Object.freeze(layers) });
}

/** Remove only the layers and source belonging to this release namespace. */
export function removeReleaseMapLayers(map: MapLike, namespace: string): void {
  const { source, layers } = ids(namespace);
  for (const id of [...layers].reverse()) {
    if (map.getLayer(id)) map.removeLayer(id);
  }
  if (map.getSource(source)) map.removeSource(source);
}
