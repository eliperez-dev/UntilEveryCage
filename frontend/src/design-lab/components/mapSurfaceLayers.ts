/**
 * Declarative layer identifiers and expressions shared by MapSurface's two data
 * paths. The JSON path is retained for local fixtures; the real preview path is
 * served as authenticated, same-origin MVT through Vite's private proxy.
 */

import type { Map as MapLibreMap } from 'maplibre-gl';
import { baseRasterPaint, createBaseStyle, type BasemapKind } from '../../map/baseMapStyle';
export { baseRasterPaint, createBaseStyle };
export type { BasemapKind };

export const JSON_LOCATION_LAYER_IDS = [
  'clusters',
  'aggregate-outer',
  'approximate-reference-area-fill',
  'approximate-reference-area-outline',
  'approx-reference-pins',
  'approx-reference-shadows',
  'approx-reference-circles',
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

type ReferenceAreaFeature = Readonly<{
  type: 'Feature';
  properties: Record<string, string>;
  geometry: Readonly<{ type: 'Polygon'; coordinates: [number, number][][] }>;
}>;

const emptyReferenceAreas = () => ({ type: 'FeatureCollection' as const, features: [] as ReferenceAreaFeature[] });

/** Construct one great-circle polygon at a fixed surface distance from a point. */
function geodesicReferenceArea(
  key: string,
  keyProperty: string,
  longitude: number,
  latitude: number,
  radiusKm: number,
): ReferenceAreaFeature | null {
  if (!key || !Number.isFinite(longitude) || longitude < -180 || longitude > 180
    || !Number.isFinite(latitude) || latitude < -90 || latitude > 90
    || !Number.isFinite(radiusKm) || radiusKm <= 0) return null;

  const earthRadiusKm = 6371.0088;
  const angular = radiusKm / earthRadiusKm;
  const lat1 = latitude * Math.PI / 180;
  const lon1 = longitude * Math.PI / 180;
  const ring: [number, number][] = [];
  for (let bearing = 0; bearing <= 360; bearing += 15) {
    const bearingRad = bearing * Math.PI / 180;
    const lat2 = Math.asin(Math.sin(lat1) * Math.cos(angular)
      + Math.cos(lat1) * Math.sin(angular) * Math.cos(bearingRad));
    const lon2 = lon1 + Math.atan2(
      Math.sin(bearingRad) * Math.sin(angular) * Math.cos(lat1),
      Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2),
    );
    ring.push([((lon2 * 180 / Math.PI + 540) % 360) - 180, lat2 * 180 / Math.PI]);
  }
  return {
    type: 'Feature',
    properties: { [keyProperty]: key },
    geometry: { type: 'Polygon', coordinates: [ring] },
  };
}

/** Return at most one fixed-radius area, only for the selected public approximate point. */
export function createSelectedApproximateReferenceArea(
  features: readonly any[],
  selectedKey: string | null | undefined,
  radiusKm: number,
) {
  if (!selectedKey) return emptyReferenceAreas();
  const point = features.find(feature => feature?.properties?.key === selectedKey
    && feature?.properties?.kind === 'reference'
    && feature?.properties?.precision === 'approximate'
    && feature?.geometry?.type === 'Point');
  const coordinates = point?.geometry?.coordinates;
  if (!Array.isArray(coordinates) || coordinates.length < 2) return emptyReferenceAreas();
  const area = geodesicReferenceArea(selectedKey, 'key', Number(coordinates[0]), Number(coordinates[1]), radiusKm);
  return area ? { type: 'FeatureCollection' as const, features: [area] } : emptyReferenceAreas();
}

/**
 * Build geographic, selected-only reference areas for every point-based
 * approximate MVT feature. This keeps display geometry in degrees rather than
 * using a constant pixel halo, including for coarse references.
 */
export function createMvtReferenceAreas(features: readonly any[], radiusKm: number) {
  const unique = new Map<string, unknown>();
  for (const feature of features) {
    if (!isMvtReferenceKind(feature?.properties?.kind) || feature?.geometry?.type !== 'Point') continue;
    const key = feature.properties?.feature_key;
    const coordinates = feature.geometry.coordinates;
    if (typeof key !== 'string' || !Array.isArray(coordinates) || coordinates.length < 2 || unique.has(key)) continue;
    const longitude = Number(coordinates[0]);
    const latitude = Number(coordinates[1]);
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) continue;
    const area = geodesicReferenceArea(key, 'feature_key', longitude, latitude, radiusKm);
    if (area) unique.set(key, area);
  }
  return { type: 'FeatureCollection' as const, features: [...unique.values()] };
}

type MapLike = {
  addSource(id: string, source: unknown): void;
  addLayer(layer: unknown): void;
  getLayer(id: string): unknown;
  getSource(id: string): unknown;
  removeLayer(id: string): void;
  removeSource(id: string): void;
};

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
  const source = MVT_SOURCE_ID;
  const sourceLayer = MVT_SOURCE_LAYER;

  map.addLayer({
    id: 'mvt-approx-reference-area', type: 'fill', source: 'mvt-reference-areas',
    paint: { 'fill-color': '#d8473f', 'fill-opacity': 0 },
  });
  map.addLayer({
    id: 'mvt-approx-reference-outline', type: 'line', source: 'mvt-reference-areas',
    paint: { 'line-color': '#ff695c', 'line-opacity': 0, 'line-width': 2 },
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
    id: 'mvt-reference-center', type: 'symbol', source, 'source-layer': sourceLayer,
    filter: references,
    layout: {
      'icon-image': 'v1-pin-grey', 'icon-anchor': 'bottom', 'icon-size': 0.5,
      'icon-allow-overlap': true, 'icon-ignore-placement': true,
    },
    paint: { 'icon-opacity': 0.95 },
  });
  map.addLayer({
    id: 'mvt-reference-count', type: 'symbol', source, 'source-layer': sourceLayer,
    filter: references,
    layout: { 'text-field': ['case', ['>', count, 1], ['to-string', count], ''], 'text-font': ['Open Sans Bold'], 'text-size': 12 },
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
  if (map.getSource('approximate-reference-area')) map.removeSource('approximate-reference-area');
  if (map.getSource('mvt-reference-areas')) map.removeSource('mvt-reference-areas');
  if (map.getSource(MVT_SOURCE_ID)) map.removeSource(MVT_SOURCE_ID);
}
