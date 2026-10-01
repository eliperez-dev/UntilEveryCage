/**
 * Declarative layer identifiers and expressions shared by MapSurface's two data
 * paths. The JSON path is retained for local fixtures; the real preview path is
 * served as authenticated, same-origin MVT through Vite's private proxy.
 */

import type { Map as MapLibreMap } from 'maplibre-gl';

export const JSON_LOCATION_LAYER_IDS = [
  'clusters',
  'aggregate-outer',
  'approx-reference-points',
  'aggregate-count',
  'aggregate-kind',
  'approximate-points',
  'source-coordinate-points',
  'v1-source-shadows',
  'v1-source-pins',
  'exact-shadows',
  'exact-pins',
] as const;

export const MVT_LOCATION_LAYER_IDS = [
  'mvt-clusters',
  'mvt-approx-reference-area',
  'mvt-approx-reference-outline',
  'mvt-reference-center',
  'mvt-reference-outer',
  'mvt-reference-count',
  'mvt-reference-kind',
  'mvt-source-coordinates',
  'mvt-v1-source-shadows',
  'mvt-v1-source-pins',
] as const;

export const MVT_SOURCE_ID = 'preview-mvt';
export const MVT_SOURCE_LAYER = 'uec_preview';

export function mvtTileUrl(sourceId?: string, clusterCutoff = 7.5): string[] {
  const sourceFilter = sourceId ? `&source_id=${encodeURIComponent(sourceId)}` : '';
  return [`/dev/real-preview/map/tiles/{z}/{x}/{y}?cluster_cutoff=${clusterCutoff}${sourceFilter}`];
}

/** Change the MVT hierarchy cutoff while retaining the cached vector-source contract. */
export function setMvtClusterCutoff(map: MapLibreMap, sourceId: string | undefined, cutoff: number): void {
  const source = map.getSource(MVT_SOURCE_ID) as ({ roundZoom?: boolean; setTiles?: (tiles: string[]) => unknown } | undefined);
  if (!source?.setTiles || !Number.isFinite(cutoff) || cutoff < 4 || cutoff > 14 || Math.round(cutoff * 2) !== cutoff * 2) return;
  try { source.roundZoom = !Number.isInteger(cutoff); } catch { /* The server-side cutoff remains authoritative. */ }
  source.setTiles(mvtTileUrl(sourceId, cutoff));
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

export type BasemapKind = 'vector' | 'muted' | 'satellite';

/** Desaturate existing OSM imagery without adding a provider or tile request. */
export function baseRasterPaint(basemap: BasemapKind): Record<string, number> {
  return basemap === 'muted'
    ? { 'raster-saturation': -1, 'raster-contrast': 0.12, 'raster-brightness-min': 0.08, 'raster-brightness-max': 0.92 }
    : { 'raster-saturation': 0, 'raster-contrast': 0, 'raster-brightness-min': 0, 'raster-brightness-max': 1 };
}

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
      { id: 'base', type: 'raster', source: 'base', paint: baseRasterPaint(basemap) },
      { id: 'transport', type: 'raster', source: 'transport', paint: { 'raster-opacity': basemap === 'satellite' ? 0.72 : 0 } },
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
    promoteId: { [MVT_SOURCE_LAYER]: 'feature_key' },
    minzoom: 0,
    maxzoom: 14,
    roundZoom: true,
  });
  map.addSource('mvt-reference-areas', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  });

  const kind = (value: string) => ['==', ['get', 'kind'], value];
  const count = ['coalesce', ['get', 'count'], 1];
  const references = ['any', kind('city_reference'), kind('coarse_reference')];
  const referenceStroke = ['match', ['get', 'kind'], 'city_reference', '#86aeca', '#c9a36e'];
  const referenceFill = ['match', ['get', 'kind'], 'city_reference', '#15252c', '#292117'];
  const source = MVT_SOURCE_ID;
  const sourceLayer = MVT_SOURCE_LAYER;

  map.addLayer({
    id: 'mvt-approx-reference-area', type: 'fill', source: 'mvt-reference-areas',
    paint: { 'fill-color': '#79b9da', 'fill-opacity': 0.14 },
  });
  map.addLayer({
    id: 'mvt-approx-reference-outline', type: 'line', source: 'mvt-reference-areas',
    paint: { 'line-color': '#79b9da', 'line-opacity': 0.48, 'line-width': 1 },
  });
  map.addLayer({
    id: 'mvt-clusters', type: 'symbol', source, 'source-layer': sourceLayer,
    filter: kind('cluster'),
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
    filter: kind('coarse_reference'),
    paint: { 'circle-color': referenceFill, 'circle-radius': 18, 'circle-opacity': 0.96, 'circle-stroke-color': referenceStroke, 'circle-stroke-width': 3 },
  });
  map.addLayer({
    id: 'mvt-reference-center', type: 'symbol', source, 'source-layer': sourceLayer,
    filter: kind('city_reference'),
    layout: {
      'icon-image': 'cluster-approx', 'icon-size': 0.8,
      'icon-allow-overlap': true, 'icon-ignore-placement': true,
    },
    paint: { 'icon-opacity': 0.95 },
  });
  map.addLayer({
    id: 'mvt-reference-count', type: 'symbol', source, 'source-layer': sourceLayer,
    filter: references,
    layout: { 'text-field': ['to-string', count], 'text-font': ['Open Sans Bold'], 'text-size': 12 },
    paint: { 'text-color': '#f1efe8' },
  });
  map.addLayer({
    id: 'mvt-reference-kind', type: 'symbol', source, 'source-layer': sourceLayer,
    filter: references,
    layout: { 'visibility': 'none', 'text-field': ['match', ['get', 'kind'], 'city_reference', 'CITY REF', 'AREA REF'], 'text-font': ['Open Sans Bold'], 'text-size': 9, 'text-offset': [0, 2.8], 'text-allow-overlap': true, 'text-ignore-placement': true },
    paint: { 'text-color': referenceStroke, 'text-halo-color': '#171a18', 'text-halo-width': 1.5 },
  });
  map.addLayer({
    id: 'mvt-source-coordinates', type: 'circle', source, 'source-layer': sourceLayer,
    filter: kind('source_coordinate'),
    paint: { 'circle-radius': 7, 'circle-color': ['match', ['get', 'precision'], 'source_provided_unverified', '#e0a45d', '#d8c99b'], 'circle-opacity': 0.94, 'circle-stroke-color': '#171a18', 'circle-stroke-width': 2.5 },
  });
  map.addLayer({
    id: 'mvt-v1-source-shadows', type: 'symbol', source, 'source-layer': sourceLayer,
    filter: kind('source_coordinate'),
    layout: { visibility: 'none', 'icon-image': 'v1-pin-shadow', 'icon-anchor': 'bottom', 'icon-size': 1,
      'icon-offset': [8.5, 0], 'icon-allow-overlap': true, 'icon-ignore-placement': true },
  });
  map.addLayer({
    id: 'mvt-v1-source-pins', type: 'symbol', source, 'source-layer': sourceLayer,
    filter: kind('source_coordinate'),
    layout: { visibility: 'none', 'icon-image': 'v1-pin-red', 'icon-anchor': 'bottom', 'icon-size': 0.5,
      'icon-allow-overlap': true, 'icon-ignore-placement': true },
  });
}

export function removeLocationLayers(map: MapLike): void {
  for (const id of [...JSON_LOCATION_LAYER_IDS, ...MVT_LOCATION_LAYER_IDS]) {
    if (map.getLayer(id)) map.removeLayer(id);
  }
  if (map.getSource('locations')) map.removeSource('locations');
  if (map.getSource('mvt-reference-areas')) map.removeSource('mvt-reference-areas');
  if (map.getSource(MVT_SOURCE_ID)) map.removeSource(MVT_SOURCE_ID);
}
