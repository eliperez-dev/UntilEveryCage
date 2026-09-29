/** Release-scoped public MVT layers. Features are already privacy-filtered and
 * clustered by the server; the browser never receives a facility feed. */

export const RELEASE_MAP_SOURCE_LAYER = 'uec_map';

/** The only properties the public map projection may expose. */
export const RELEASE_MAP_PROPERTIES = [
  'feature_key', 'kind', 'count', 'exact_count', 'coarse_count',
  'next_zoom', 'record_id', 'category_key',
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
};

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
    id: layers[5], type: 'circle', source, 'source-layer': sourceLayer,
    filter: kind('exact'),
    paint: {
      'circle-radius': 6.5, 'circle-color': ['match', ['get', 'category_key'],
        'slaughter', '#a95d55', 'processing', '#89939a', 'laboratory', '#9882b5',
        'farm', '#b4955c', 'dealer', '#b8754d', 'exhibitor', '#6e997d', '#d8c99b'],
      'circle-opacity': 0.94 * opacity,
      'circle-stroke-color': '#171a18', 'circle-stroke-width': 2.5,
      'circle-stroke-opacity': opacity,
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
