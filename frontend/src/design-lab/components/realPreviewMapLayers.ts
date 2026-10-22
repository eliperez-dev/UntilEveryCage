import type { Map as MapLibreMap } from 'maplibre-gl';
import type { JsonMapCollection } from './jsonMapFallback';
import { CATEGORY_PRESENTATIONS, CATEGORY_PRIMARY_BY_SOURCE_KEY } from '../../features/locations/categoryPresentation';

export const DEFAULT_CLUSTER_RADIUS = 30;
/** Requested camera zoom. Native GeoJSON tile zooms are whole numbers. */
export const DEFAULT_CLUSTER_MAX_ZOOM = 7.5;
/** Presentation-only radius when the public projection has no supplied area. */
/** Selected approximate locations receive a 500m-diameter reference area. */
export const DEFAULT_REFERENCE_RADIUS_KM = 0.25;
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

const cityReference = ['any', ['==', ['get', 'precision'], 'city'], ['==', ['get', 'precision'], 'city_reference_approximate'], ['==', ['get', 'precision'], 'provider_locality_approximate'], ['==', ['get', 'precision'], 'locality_reference_coarse']];
const categoryPairs = Object.entries(CATEGORY_PRIMARY_BY_SOURCE_KEY);
const categoryColorBySourceKey = ['match', ['get', 'category_key'], ...categoryPairs.flatMap(([sourceKey, primaryKey]) => [sourceKey, CATEGORY_PRESENTATIONS[primaryKey].color]), CATEGORY_PRESENTATIONS.unclassified.color];
const v1PinByPrimary = {
  animal_keeping_and_production: 'v1-pin-green',
  slaughter: 'v1-pin-red',
  processing_and_preparation: 'v1-pin-grey',
  research_and_animal_use: 'v1-pin-violet',
  other_regulated_premises: 'v1-pin-orange',
  unclassified: 'v1-pin-grey',
} as const;
const v1PinBySourceKey = ['match', ['get', 'category_key'], ...categoryPairs.flatMap(([sourceKey, primaryKey]) => [sourceKey, v1PinByPrimary[primaryKey]]), 'v1-pin-grey'];
// Corrected feeds provide complete taxonomy keys. Prefer those over a legacy
// scalar category so normal circles and V1 assets always share one palette.
const categoryFromKeys = (fallback: unknown): unknown[] => ['case',
  ['in', 'slaughter', ['get', 'category_keys']], CATEGORY_PRESENTATIONS.slaughter.color,
  ['in', 'research_and_animal_use', ['get', 'category_keys']], CATEGORY_PRESENTATIONS.research_and_animal_use.color,
  ['in', 'processing_and_preparation', ['get', 'category_keys']], CATEGORY_PRESENTATIONS.processing_and_preparation.color,
  ['in', 'animal_keeping_and_production', ['get', 'category_keys']], CATEGORY_PRESENTATIONS.animal_keeping_and_production.color,
  ['in', 'other_regulated_premises', ['get', 'category_keys']], CATEGORY_PRESENTATIONS.other_regulated_premises.color,
  fallback,
];
const categoryColor = categoryFromKeys(categoryColorBySourceKey);
const v1CategoryPin = ['case',
  ['in', 'slaughter', ['get', 'category_keys']], v1PinByPrimary.slaughter,
  ['in', 'research_and_animal_use', ['get', 'category_keys']], v1PinByPrimary.research_and_animal_use,
  ['in', 'processing_and_preparation', ['get', 'category_keys']], v1PinByPrimary.processing_and_preparation,
  ['in', 'animal_keeping_and_production', ['get', 'category_keys']], v1PinByPrimary.animal_keeping_and_production,
  ['in', 'other_regulated_premises', ['get', 'category_keys']], v1PinByPrimary.other_regulated_premises,
  v1PinBySourceKey,
];
export const REAL_PREVIEW_LAYER_IDS = [
  'clusters', 'approximate-reference-area-fill', 'approximate-reference-area-outline',
  'aggregate-outer', 'approx-reference-pins', 'approx-reference-shadows', 'approx-reference-circles', 'approx-reference-points', 'aggregate-count',
  'aggregate-kind', 'source-coordinate-points', 'v1-source-shadows', 'v1-source-pins',
] as const;

export function hasRealPreviewMapLayers(map: Pick<MapLibreMap, 'getSource' | 'getLayer'>): boolean {
  return Boolean(map.getSource('locations')) && REAL_PREVIEW_LAYER_IDS.every((id) => Boolean(map.getLayer(id)));
}

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
    clusterProperties: {
      representedCount: ['+', ['get', 'weight']],
      approximateCount: ['+', ['case', ['any', ['==', ['get', 'precision'], 'approximate'], ['==', ['get', 'precision'], 'city'], ['==', ['get', 'precision'], 'locality_reference_coarse']], ['get', 'weight'], 0]],
    },
  } as any);
  map.addSource('approximate-reference-area', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  });

  const unclustered = ['!', ['has', 'cluster']];
  const representedCount = ['get', 'representedCount'];
  const approximateCount = ['get', 'approximateCount'];
  const countPalette = (prefix: string) => ['step', representedCount, `${prefix}-low`, 10, `${prefix}-mid`, 100, `${prefix}-high`, 1001, `${prefix}-very-high`];
  map.addLayer({
    id: 'clusters', type: 'symbol', source: 'locations', filter: ['has', 'cluster'],
    layout: {
      // Cluster colour expresses record count only. Precision remains visible
      // through the red reference ring, not a competing cluster palette.
      'icon-image': countPalette('cluster'),
      'icon-size': 1, 'icon-allow-overlap': true, 'icon-ignore-placement': true,
      'text-field': ['to-string', representedCount], 'text-font': ['Open Sans Bold'], 'text-size': 12,
      'text-allow-overlap': true, 'text-ignore-placement': true,
    },
    paint: { 'text-color': '#172019' },
  } as any);

  const referenceKind = ['in', ['get', 'kind'], ['literal', ['reference', 'provider_locality_approximate']]];
  // Only records explicitly projected as references receive the uncertainty
  // halo. Source-reported coordinates are not coarse merely because their
  // precision has not been independently verified.
  const reference = ['all', unclustered, referenceKind];
  const aggregateReference = ['all', unclustered, referenceKind];
  const approximateReference = ['all', ...aggregateReference.slice(1), ['==', ['get', 'precision'], 'approximate']];
  const cityReferenceArea = ['all', ...reference.slice(1), cityReference];
  const weight = ['get', 'weight'];
  map.addLayer({
    id: 'approximate-reference-area-fill', type: 'fill', source: 'approximate-reference-area',
    paint: { 'fill-color': '#d8473f', 'fill-opacity': 0.16 },
  } as any);
  map.addLayer({
    id: 'approximate-reference-area-outline', type: 'line', source: 'approximate-reference-area',
    paint: { 'line-color': '#ff695c', 'line-opacity': 0.92, 'line-width': 2 },
  } as any);
  map.addLayer({
    id: 'aggregate-outer', type: 'circle', source: 'locations', filter: cityReferenceArea,
    paint: {
      'circle-color': '#d8473f',
      'circle-radius': referenceRadiusExpression(DEFAULT_REFERENCE_RADIUS_KM),
      // A reference area is shown only for the inspected approximate record.
      // It is a 250m radius presentation aid, never an accuracy assertion.
      'circle-opacity': 0,
      'circle-stroke-color': '#ff695c',
      'circle-stroke-width': 2.5,
      'circle-stroke-opacity': 0,
    },
  } as any);
  // Approximate singleton records use the same category pin family as
  // source-coordinate facilities. The fallback circles serve debug mode only.
  map.addLayer({
    id: 'approx-reference-circles', type: 'circle', source: 'locations',
    filter: approximateReference,
    layout: { visibility: 'visible' },
    paint: {
      'circle-radius': 6.5,
      'circle-color': categoryColor,
      'circle-opacity': 0.94,
      'circle-stroke-color': '#171a18',
      'circle-stroke-width': 2.5,
    },
  } as any);
  map.addLayer({
    id: 'approx-reference-shadows', type: 'symbol', source: 'locations', filter: approximateReference,
    layout: { visibility: 'none', 'icon-image': 'v1-pin-shadow', 'icon-anchor': 'bottom',
      'icon-size': 1, 'icon-offset': [8.5, 0], 'icon-allow-overlap': true, 'icon-ignore-placement': true },
  } as any);
  map.addLayer({
    id: 'approx-reference-pins', type: 'symbol', source: 'locations', filter: approximateReference,
    layout: { visibility: 'none', 'icon-image': v1CategoryPin, 'icon-anchor': 'bottom', 'icon-size': 0.5,
      'icon-allow-overlap': true, 'icon-ignore-placement': true,
      'text-field': ['case', ['>', weight, 1], ['to-string', weight], ''], 'text-font': ['Open Sans Bold'], 'text-size': 11,
      'text-allow-overlap': true, 'text-ignore-placement': true },
    paint: { 'text-color': '#172019' },
  } as any);
  setClusterTileRounding(map, settings.maxZoom);
  // The map-scale disc sits behind a permanent center mark. At low zoom the
  // disc is subpixel, while the center still makes the reference discoverable.
  map.addLayer({
    id: 'approx-reference-points', type: 'symbol', source: 'locations',
    filter: ['all', ...aggregateReference.slice(1), cityReference],
    layout: {
      // A singleton remains an ordinary muted pin, not a misleading numeric
      // cluster badge. The selected-only red area carries the approximation cue.
      'icon-image': 'v1-pin-grey', 'icon-anchor': 'bottom', 'icon-size': 0.5,
      'icon-allow-overlap': true, 'icon-ignore-placement': true,
      'text-field': ['case', ['>', weight, 1], ['to-string', weight], ''], 'text-font': ['Open Sans Bold'], 'text-size': 11,
      'text-allow-overlap': true, 'text-ignore-placement': true,
    },
    paint: { 'text-color': '#172019' },
  } as any);
  map.addLayer({
    id: 'aggregate-count', type: 'symbol', source: 'locations',
    filter: ['all', ...aggregateReference.slice(1), ['!', cityReference]],
    layout: { 'text-field': ['case', ['>', weight, 1], ['to-string', weight], ''], 'text-font': ['Open Sans Bold'], 'text-size': 12 },
    paint: { 'text-color': '#f1efe8', 'text-halo-color': '#15252c', 'text-halo-width': 1 },
  } as any);
  map.addLayer({
    id: 'aggregate-kind', type: 'symbol', source: 'locations', filter: aggregateReference,
    layout: { 'visibility': 'none', 'text-field': ['case', cityReference, 'APPROX', 'AREA REF'], 'text-font': ['Open Sans Bold'], 'text-size': 9, 'text-offset': [0, 2.8], 'text-allow-overlap': true, 'text-ignore-placement': true },
    paint: { 'text-color': '#ff9c93', 'text-halo-color': '#171a18', 'text-halo-width': 1.5 },
  } as any);

  const coordinate = ['all', unclustered, ['in', ['get', 'kind'], ['literal', ['source-coordinate', 'provider_address_point_private']]]];
  map.addLayer({
    id: 'source-coordinate-points', type: 'circle', source: 'locations', filter: coordinate,
    paint: { 'circle-radius': 7, 'circle-color': categoryColor, 'circle-opacity': 0.94, 'circle-stroke-color': '#171a18', 'circle-stroke-width': 2.5 },
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
    layout: { 'visibility': 'none', 'icon-image': v1CategoryPin, 'icon-anchor': 'bottom',
      'icon-size': 0.5, 'icon-allow-overlap': true, 'icon-ignore-placement': true },
  } as any);
}

export async function setRealPreviewPinMode(map: MapLibreMap, enabled: boolean, baseUrl: string): Promise<void> {
  if (enabled) {
    for (const [id, file] of [['v1-pin-red', 'marker-icon-2x-red.png'], ['v1-pin-green', 'marker-icon-2x-green.png'], ['v1-pin-yellow', 'marker-icon-2x-yellow.png'], ['v1-pin-violet', 'marker-icon-2x-violet.png'], ['v1-pin-orange', 'marker-icon-2x-orange.png'], ['v1-pin-grey', 'marker-icon-2x-grey.png'], ['v1-pin-shadow', 'marker-shadow.png']] as const) {
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
  if (map.getLayer('approx-reference-circles')) map.setLayoutProperty('approx-reference-circles', 'visibility', enabled ? 'none' : 'visible');
  if (map.getLayer('approx-reference-shadows')) map.setLayoutProperty('approx-reference-shadows', 'visibility', enabled ? 'visible' : 'none');
  if (map.getLayer('approx-reference-pins')) map.setLayoutProperty('approx-reference-pins', 'visibility', enabled ? 'visible' : 'none');
}

/** Paint/layout changes do not rebuild the full 39k-unit cluster index. */
export function applyRealPreviewVisualSettings(map: MapLibreMap, settings: RealPreviewVisualSettings): void {
  if (!map.getLayer('aggregate-outer')) return;
  map.setPaintProperty('aggregate-outer', 'circle-radius', referenceRadiusExpression(settings.referenceRadiusKm) as any);
  const selected = settings.selectedKey
    ? ['==', ['get', 'key'], settings.selectedKey]
    : false;
  map.setPaintProperty('aggregate-outer', 'circle-opacity', ['case', selected, Math.min(0.34, settings.referenceOpacity + 0.12), 0] as any);
  map.setPaintProperty('aggregate-outer', 'circle-stroke-opacity', ['case', selected, Math.min(1, Math.max(0.62, settings.referenceOpacity * 2 + 0.52)), 0] as any);
  map.setPaintProperty('source-coordinate-points', 'circle-radius', settings.coordinateRadius);
  if (map.getLayer('approx-reference-circles')) map.setPaintProperty('approx-reference-circles', 'circle-radius', settings.coordinateRadius);
  map.setLayoutProperty('aggregate-kind', 'visibility', settings.showReferenceLabels ? 'visible' : 'none');
}

export function setRealPreviewMapData(map: MapLibreMap, data: JsonMapCollection): boolean {
  const source = map.getSource('locations') as any;
  if (!source?.setData) return false;
  source.setData(data);
  return true;
}

/** Category selection filters individual public coordinate marks; clusters and city references remain neutral context. */
export function setRealPreviewCategoryFilter(map: MapLibreMap, categories: readonly string[]): void {
  if (!map.getLayer('source-coordinate-points')) return;
  const base = ['all', ['!', ['has', 'cluster']], ['in', ['get', 'kind'], ['literal', ['source-coordinate', 'provider_address_point_private']]]];
  const categoryFilter = categories.length
    ? ['any', ...categories.map(key => ['in', key, ['get', 'category_keys']])]
    : true;
  const filter = categoryFilter === true ? base : ['all', base, categoryFilter];
  map.setFilter('source-coordinate-points', filter as any);
  if (map.getLayer('v1-source-pins')) map.setFilter('v1-source-pins', filter as any);
  if (map.getLayer('v1-source-shadows')) map.setFilter('v1-source-shadows', filter as any);
}
