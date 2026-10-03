import type { Map as MapLibreMap } from 'maplibre-gl';
import type { JsonMapCollection } from './jsonMapFallback';

export const DEFAULT_CLUSTER_RADIUS = 30;
/** Requested camera zoom. Native GeoJSON tile zooms are whole numbers. */
export const DEFAULT_CLUSTER_MAX_ZOOM = 7.5;
export const DEFAULT_REFERENCE_RADIUS_KM = 3;
export const APPROX_MARKER_SCALE = 0.8;

export type RealPreviewClusterSettings = Readonly<{
  enabled: boolean;
  radius: number;
  maxZoom: number;
}>;

/** Set the last clustered tile zoom, not the requested camera threshold. */
export function nativeClusterMaxZoom(cameraCutoff: number): number {
  return Math.max(0, Math.ceil(cameraCutoff) - 1);
}

/**
 * MapLibre's GeoJSON source normally selects tiles with floor(camera zoom).
 * Its internal roundZoom source flag selects the next tile at half zoom. We
 * only opt into that behavior for half-zoom cutoffs, so native clusters and
 * unclustered records switch together at the requested camera zoom.
 */
export function useRoundedClusterTiles(cameraCutoff: number): boolean {
  return !Number.isInteger(cameraCutoff);
}

export function setClusterTileRounding(map: MapLibreMap, cameraCutoff: number): boolean {
  const source = map.getSource('locations') as ({ roundZoom?: boolean } | undefined);
  if (!source) return false;
  const requested = useRoundedClusterTiles(cameraCutoff);
  try { source.roundZoom = requested; } catch { return false; }
  return source.roundZoom === requested;
}

export type RealPreviewVisualSettings = Readonly<{
  referenceRadiusKm: number;
  referenceOpacity: number;
  coordinateRadius: number;
  showReferenceLabels: boolean;
  selectedKey?: string | null;
}>;

const cityReference = ['any', ['==', ['get', 'precision'], 'city'], ['==', ['get', 'precision'], 'city_reference_approximate'], ['==', ['get', 'precision'], 'provider_locality_approximate']];

/** Pixel radius of a map-scale distance at each feature's latitude. */
export function referenceRadiusExpression(radiusKm: number): unknown[] {
  const metres = radiusKm * 1000;
  const pixelsAtZoomZero = ['/', metres, ['*', 156543.03392, ['get', 'cosLatitude']]];
  // MapLibre requires zoom to be the outermost expression for a composite
  // feature/zoom paint property.
  return ['interpolate', ['exponential', 2], ['zoom'],
    0, ['case', cityReference, pixelsAtZoomZero, 18],
    20, ['case', cityReference, ['*', 1048576, pixelsAtZoomZero], 18]];
}

/** The real-preview feed and its references share one native Supercluster index. */
export function addRealPreviewMapLayers(
  map: MapLibreMap,
  data: JsonMapCollection,
  settings: RealPreviewClusterSettings = { enabled: true, radius: DEFAULT_CLUSTER_RADIUS, maxZoom: DEFAULT_CLUSTER_MAX_ZOOM },
): void {
  if (map.getSource('locations')) return;
  map.addSource('locations', {
    type: 'geojson',
    data,
    cluster: settings.enabled,
    clusterRadius: settings.radius,
    // Above the configured cutoff, reveal every coordinate record. Approximate references
    // remain weighted aggregates rather than turning into facility pins.
    clusterMaxZoom: nativeClusterMaxZoom(settings.maxZoom),
    clusterProperties: { representedCount: ['+', ['get', 'weight']] },
  } as any);

  const unclustered = ['!', ['has', 'cluster']];
  const representedCount = ['get', 'representedCount'];
  map.addLayer({
    id: 'clusters', type: 'symbol', source: 'locations', filter: ['has', 'cluster'],
    layout: {
      'icon-image': ['step', representedCount, 'cluster-low', 10, 'cluster-mid', 100, 'cluster-high', 1001, 'cluster-very-high'],
      'icon-size': 1, 'icon-allow-overlap': true, 'icon-ignore-placement': true,
      'text-field': ['to-string', representedCount], 'text-font': ['Open Sans Bold'], 'text-size': 12,
      'text-allow-overlap': true, 'text-ignore-placement': true,
    },
    paint: { 'text-color': '#172019' },
  } as any);

  const reference = ['all', unclustered, ['in', ['get', 'kind'], ['literal', ['reference', 'provider_locality_approximate']]]];
  const weight = ['get', 'weight'];
  map.addLayer({
    id: 'aggregate-outer', type: 'circle', source: 'locations', filter: reference,
    paint: {
      'circle-color': ['case', cityReference, '#79b9da', '#15252c'],
      'circle-radius': referenceRadiusExpression(DEFAULT_REFERENCE_RADIUS_KM),
      // The full 3 km geometry remains visible and clickable, but a very light
      // wash prevents dense city references from obscuring the basemap.
      'circle-opacity': ['case', cityReference, 0.08, 0.96],
      'circle-stroke-color': ['case', cityReference, '#79b9da', '#86aeca'],
      'circle-stroke-width': ['case', cityReference, 1, 3],
      'circle-stroke-opacity': ['case', cityReference, 0.42, 1],
    },
  } as any);
  setClusterTileRounding(map, settings.maxZoom);
  // The map-scale disc sits behind a permanent center mark. At low zoom the
  // disc is subpixel, while the center still makes the reference discoverable.
  map.addLayer({
    id: 'approx-reference-points', type: 'symbol', source: 'locations',
    filter: ['all', ...reference.slice(1), cityReference],
    layout: {
      'icon-image': 'cluster-approx', 'icon-size': APPROX_MARKER_SCALE,
      'icon-allow-overlap': true, 'icon-ignore-placement': true,
      'text-field': ['to-string', weight], 'text-font': ['Open Sans Bold'], 'text-size': 11,
      'text-allow-overlap': true, 'text-ignore-placement': true,
    },
    paint: { 'text-color': '#172019' },
  } as any);
  map.addLayer({
    id: 'aggregate-count', type: 'symbol', source: 'locations',
    filter: ['all', ...reference.slice(1), ['!', cityReference]],
    layout: { 'text-field': ['to-string', weight], 'text-font': ['Open Sans Bold'], 'text-size': 12 },
    paint: { 'text-color': '#f1efe8', 'text-halo-color': '#15252c', 'text-halo-width': 1 },
  } as any);
  map.addLayer({
    id: 'aggregate-kind', type: 'symbol', source: 'locations', filter: reference,
    layout: { 'visibility': 'none', 'text-field': ['case', cityReference, 'APPROX', 'AREA REF'], 'text-font': ['Open Sans Bold'], 'text-size': 9, 'text-offset': [0, 2.8], 'text-allow-overlap': true, 'text-ignore-placement': true },
    paint: { 'text-color': '#86aeca', 'text-halo-color': '#171a18', 'text-halo-width': 1.5 },
  } as any);

  const coordinate = ['all', unclustered, ['in', ['get', 'kind'], ['literal', ['source-coordinate', 'provider_address_point_private']]]];
  map.addLayer({
    id: 'source-coordinate-points', type: 'circle', source: 'locations', filter: coordinate,
    paint: { 'circle-radius': 7, 'circle-color': ['match', ['get', 'precision'], 'source_provided_unverified', '#e0a45d', '#d8c99b'], 'circle-opacity': 0.94, 'circle-stroke-color': '#171a18', 'circle-stroke-width': 2.5 },
  } as any);
  // Exact V1 raster assets, anchored at the record coordinate as Leaflet did.
  // They remain hidden unless explicitly selected in the local debug menu.
  map.addLayer({
    id: 'v1-source-shadows', type: 'symbol', source: 'locations', filter: coordinate,
    layout: { 'visibility': 'none', 'icon-image': 'v1-pin-shadow', 'icon-anchor': 'bottom',
      'icon-size': 1, 'icon-offset': [8.5, 0], 'icon-allow-overlap': true, 'icon-ignore-placement': true },
  } as any);
  map.addLayer({
    id: 'v1-source-pins', type: 'symbol', source: 'locations', filter: coordinate,
    layout: { 'visibility': 'none', 'icon-image': 'v1-pin-red', 'icon-anchor': 'bottom',
      'icon-size': 0.5, 'icon-allow-overlap': true, 'icon-ignore-placement': true },
  } as any);
}

export async function setRealPreviewPinMode(map: MapLibreMap, enabled: boolean, baseUrl: string): Promise<void> {
  if (enabled) {
    for (const [id, file] of [['v1-pin-red', 'marker-icon-2x-red.png'], ['v1-pin-shadow', 'marker-shadow.png']] as const) {
      if (!map.hasImage(id)) map.addImage(id, (await map.loadImage(`${baseUrl}${file}`)).data);
    }
  }
  if (map.getLayer('mvt-v1-source-pins')) {
    map.setLayoutProperty('mvt-source-coordinates', 'visibility', enabled ? 'none' : 'visible');
    map.setLayoutProperty('mvt-v1-source-shadows', 'visibility', enabled ? 'visible' : 'none');
    map.setLayoutProperty('mvt-v1-source-pins', 'visibility', enabled ? 'visible' : 'none');
    return;
  }
  if (!map.getLayer('v1-source-pins')) return;
  map.setLayoutProperty('source-coordinate-points', 'visibility', enabled ? 'none' : 'visible');
  map.setLayoutProperty('v1-source-shadows', 'visibility', enabled ? 'visible' : 'none');
  map.setLayoutProperty('v1-source-pins', 'visibility', enabled ? 'visible' : 'none');
}

/** Paint/layout changes do not rebuild the full 39k-unit cluster index. */
export function applyRealPreviewVisualSettings(map: MapLibreMap, settings: RealPreviewVisualSettings): void {
  if (!map.getLayer('aggregate-outer')) return;
  map.setPaintProperty('aggregate-outer', 'circle-radius', referenceRadiusExpression(settings.referenceRadiusKm) as any);
  const selected = settings.selectedKey
    ? ['==', ['get', 'key'], settings.selectedKey]
    : false;
  map.setPaintProperty('aggregate-outer', 'circle-opacity', ['case', cityReference, ['case', selected, 0.3, settings.referenceOpacity], 0.96] as any);
  map.setPaintProperty('aggregate-outer', 'circle-stroke-opacity', ['case', cityReference, Math.min(0.7, settings.referenceOpacity * 5 + 0.17), 1] as any);
  map.setPaintProperty('source-coordinate-points', 'circle-radius', settings.coordinateRadius);
  map.setLayoutProperty('aggregate-kind', 'visibility', settings.showReferenceLabels ? 'visible' : 'none');
}

export function setRealPreviewMapData(map: MapLibreMap, data: JsonMapCollection): boolean {
  const source = map.getSource('locations') as any;
  if (!source?.setData) return false;
  source.setData(data);
  return true;
}
