/**
 * Declarative layer identifiers and expressions shared by MapSurface's two data
 * paths. The JSON path is retained for local fixtures; the real preview path is
 * served as authenticated, same-origin MVT through Vite's private proxy.
 */

export const JSON_LOCATION_LAYER_IDS = [
  'clusters',
  'aggregate-outer',
  'aggregate-count',
  'aggregate-kind',
  'approximate-points',
  'source-coordinate-points',
  'exact-shadows',
  'exact-pins',
] as const;

export const MVT_LOCATION_LAYER_IDS = [
  'mvt-clusters',
  'mvt-reference-outer',
  'mvt-reference-count',
  'mvt-reference-kind',
  'mvt-source-coordinates',
] as const;

export const MVT_SOURCE_ID = 'preview-mvt';
export const MVT_SOURCE_LAYER = 'uec_preview';

/**
 * The backend controls spatial density. This component must not re-cluster MVT
 * data, otherwise tile boundaries and server lineage would diverge.
 */
export const MVT_CLUSTER_MAX_ZOOM = 10;

export function mvtTileUrl(sourceId?: string): string[] {
  const sourceFilter = sourceId
    ? `?source_id=${encodeURIComponent(sourceId)}`
    : '';

  return [`/dev/real-preview/map/tiles/{z}/{x}/{y}${sourceFilter}`];
}

export function isMvtReferenceKind(kind: unknown): boolean {
  return kind === 'city_reference' || kind === 'coarse_reference';
}

type MapLike = {
  addSource(id: string, source: unknown): void;
  addLayer(layer: unknown): void;
  getLayer(id: string): unknown;
  getSource(id: string): unknown;
  removeLayer(id: string): void;
  removeSource(id: string): void;
};

export type BasemapKind = 'vector' | 'satellite';

/** The deliberately restrained raster base style used by both data projections. */
export function createBaseStyle(basemap: BasemapKind): Record<string, unknown> {
  const base = basemap === 'satellite'
    ? {
        type: 'raster',
        tiles: [
          'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution: 'Tiles © Esri',
      }
    : {
        type: 'raster',
        tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
        attribution: '© OpenStreetMap contributors',
      };

  return {
    version: 8,
    sources: {
      base,
      transport: {
        type: 'raster',
        tiles: [
          'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}',
        ],
        tileSize: 256,
        attribution: 'Transportation © Esri',
      },
    },
    layers: [
      { id: 'base', type: 'raster', source: 'base' },
      ...(basemap === 'satellite'
        ? [{ id: 'transport', type: 'raster', source: 'transport', paint: { 'raster-opacity': 0.72 } }]
        : []),
    ],
  };
}

/**
 * Attach the server-owned MVT hierarchy. City and coarse references begin only
 * where the backend hierarchy resolves them, so they cannot masquerade as
 * facility coordinates at world scale.
 */
export function addMvtLocationLayers(map: MapLike, sourceId?: string): void {
  if (map.getSource(MVT_SOURCE_ID)) return;

  map.addSource(MVT_SOURCE_ID, {
    type: 'vector',
    tiles: mvtTileUrl(sourceId),
    minzoom: 0,
    maxzoom: 14,
  });

  const kind = (value: string) => ['==', ['get', 'kind'], value];
  const count = ['coalesce', ['get', 'count'], 1];
  const references = ['any', kind('city_reference'), kind('coarse_reference')];
  const referenceStroke = ['match', ['get', 'kind'], 'city_reference', '#86aeca', '#c9a36e'];
  const referenceFill = ['match', ['get', 'kind'], 'city_reference', '#15252c', '#292117'];
  const source = MVT_SOURCE_ID;
  const sourceLayer = MVT_SOURCE_LAYER;

  map.addLayer({
    id: 'mvt-clusters', type: 'symbol', source, 'source-layer': sourceLayer,
    minzoom: 0, maxzoom: MVT_CLUSTER_MAX_ZOOM, filter: kind('cluster'),
    layout: {
      'icon-image': ['step', count, 'cluster-low', 10, 'cluster-mid', 100, 'cluster-high'],
      'icon-size': 1, 'icon-allow-overlap': true, 'icon-ignore-placement': true,
      'text-field': ['to-string', count], 'text-font': ['Open Sans Bold'], 'text-size': 12,
      'text-allow-overlap': true, 'text-ignore-placement': true,
    },
    paint: { 'text-color': '#172019', 'icon-opacity': 1, 'text-opacity': 1 },
  });
  map.addLayer({
    id: 'mvt-reference-outer', type: 'circle', source, 'source-layer': sourceLayer,
    minzoom: MVT_CLUSTER_MAX_ZOOM, filter: references,
    paint: { 'circle-color': referenceFill, 'circle-radius': 18, 'circle-opacity': 0.96, 'circle-stroke-color': referenceStroke, 'circle-stroke-width': 3 },
  });
  map.addLayer({
    id: 'mvt-reference-count', type: 'symbol', source, 'source-layer': sourceLayer,
    minzoom: MVT_CLUSTER_MAX_ZOOM, filter: references,
    layout: { 'text-field': ['to-string', count], 'text-font': ['Open Sans Bold'], 'text-size': 12 },
    paint: { 'text-color': '#f1efe8' },
  });
  map.addLayer({
    id: 'mvt-reference-kind', type: 'symbol', source, 'source-layer': sourceLayer,
    minzoom: MVT_CLUSTER_MAX_ZOOM, filter: references,
    layout: { 'text-field': ['match', ['get', 'kind'], 'city_reference', 'CITY REF', 'AREA REF'], 'text-font': ['Open Sans Bold'], 'text-size': 9, 'text-offset': [0, 2.8], 'text-allow-overlap': true, 'text-ignore-placement': true },
    paint: { 'text-color': referenceStroke, 'text-halo-color': '#171a18', 'text-halo-width': 1.5 },
  });
  map.addLayer({
    id: 'mvt-source-coordinates', type: 'circle', source, 'source-layer': sourceLayer,
    filter: kind('source_coordinate'),
    paint: { 'circle-radius': 6.5, 'circle-color': '#d8c99b', 'circle-opacity': 0.94, 'circle-stroke-color': '#171a18', 'circle-stroke-width': 2.5 },
  });
}

export function removeLocationLayers(map: MapLike): void {
  for (const id of [...JSON_LOCATION_LAYER_IDS, ...MVT_LOCATION_LAYER_IDS]) {
    if (map.getLayer(id)) map.removeLayer(id);
  }
  if (map.getSource('locations')) map.removeSource('locations');
  if (map.getSource(MVT_SOURCE_ID)) map.removeSource(MVT_SOURCE_ID);
}
