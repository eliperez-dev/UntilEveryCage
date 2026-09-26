/**
 * The bounded GeoJSON map path used by fixtures and offline development.
 *
 * Production real-preview maps use the MVT projection instead. Keeping this
 * fallback in one module makes that boundary explicit: it projects loaded
 * records into a small GeoJSON collection, owns the matching source/layers,
 * and never calls a network endpoint or invents data.
 */
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';
import type { LabRecord } from '../contract';

export type JsonMapMode = 'synthetic' | 'real-preview';

export type JsonMapFeature = Readonly<{
  type: 'Feature';
  geometry: Readonly<{ type: 'Point'; coordinates: [number, number] }>;
  properties: Record<string, unknown>;
}>;

export type JsonMapCollection = Readonly<{
  type: 'FeatureCollection';
  features: readonly JsonMapFeature[];
}>;

/** V1 pin assets are retained only for confirmed exact fixture coordinates. */
export const PIN_COLORS: Record<string, string> = {
  Poultry: 'red',
  Pig: 'grey',
  Dairy: 'violet',
  Processing: 'yellow',
  Laboratory: 'orange',
  Aquaculture: 'green',
};

/**
 * Project the already-loaded, bounded record page into GeoJSON.
 * City and coarse records are intentionally aggregated into reference features
 * rather than emitted as misleading facility pins.
 */
export function createJsonMapCollection(
  records: readonly LabRecord[],
  mode: JsonMapMode,
): JsonMapCollection {
  const features: JsonMapFeature[] = [];
  const references = new Map<
    string,
    { first: LabRecord; members: LabRecord[]; latitude: number; longitude: number }
  >();

  for (const record of records) {
    if (record.latitude === null || record.longitude === null) continue;

    if (record.precision === 'exact') {
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [record.longitude, record.latitude] },
        properties: {
          id: record.id,
          kind: mode === 'real-preview' ? 'source-coordinate' : 'exact',
          weight: 1,
          icon: `pin-${PIN_COLORS[record.category] ?? 'red'}`,
          name: record.name,
        },
      });
      continue;
    }

    if (record.precision === 'approximate') {
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [record.longitude, record.latitude] },
        properties: { id: record.id, kind: 'approximate', weight: 1, name: record.name },
      });
      continue;
    }

    if (record.precision !== 'city' && record.precision !== 'coarse') continue;
    const key = `${record.country}\u0000${record.locality}\u0000${record.precision}`;
    const reference = references.get(key);
    if (reference) {
      reference.members.push(record);
      reference.latitude += record.latitude;
      reference.longitude += record.longitude;
    } else {
      references.set(key, {
        first: record,
        members: [record],
        latitude: record.latitude,
        longitude: record.longitude,
      });
    }
  }

  for (const [key, reference] of references) {
    const { first, members } = reference;
    features.push({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [reference.longitude / members.length, reference.latitude / members.length],
      },
      properties: {
        id: `aggregate:${key}`,
        kind: 'aggregate',
        precision: first.precision,
        weight: members.length,
        name: first.locality,
        memberIds: JSON.stringify(members.map((member) => member.id)),
      },
    });
  }

  return { type: 'FeatureCollection', features };
}

/** Add the complete fallback source and its deliberately distinct visual semantics. */
export function addJsonLocationLayers(map: MapLibreMap, data: JsonMapCollection): void {
  if (map.getSource('locations')) return;

  map.addSource('locations', {
    type: 'geojson',
    data,
    cluster: true,
    clusterRadius: 50,
    clusterMaxZoom: 9,
    clusterProperties: { representedCount: ['+', ['get', 'weight']] },
  } as any);

  const cluster = ['has', 'cluster'];
  const representedCount = ['get', 'representedCount'];

  map.addLayer({
    id: 'clusters', type: 'symbol', source: 'locations', filter: cluster,
    layout: {
      'icon-image': ['step', representedCount, 'cluster-low', 10, 'cluster-mid', 100, 'cluster-high'],
      'icon-size': 1, 'icon-allow-overlap': true, 'icon-ignore-placement': true,
      'text-field': ['to-string', representedCount], 'text-font': ['Open Sans Bold'], 'text-size': 12,
      'text-allow-overlap': true, 'text-ignore-placement': true,
    },
    paint: { 'text-color': '#172019' },
  } as any);

  const aggregate = ['all', ['!', ['has', 'cluster']], ['==', ['get', 'kind'], 'aggregate']];
  const weight = ['get', 'weight'];
  const referenceStroke = ['match', ['get', 'precision'], 'city', '#86aeca', '#c9a36e'];
  const referenceFill = ['match', ['get', 'precision'], 'city', '#15252c', '#292117'];
  map.addLayer({
    id: 'aggregate-outer', type: 'circle', source: 'locations', filter: aggregate,
    paint: { 'circle-color': referenceFill, 'circle-radius': 18, 'circle-opacity': 0.96, 'circle-stroke-color': referenceStroke, 'circle-stroke-width': 3 },
  } as any);
  map.addLayer({
    id: 'aggregate-count', type: 'symbol', source: 'locations', filter: aggregate,
    layout: { 'text-field': ['to-string', weight], 'text-font': ['Open Sans Bold'], 'text-size': 12 },
    paint: { 'text-color': '#f1efe8' },
  } as any);
  map.addLayer({
    id: 'aggregate-kind', type: 'symbol', source: 'locations', filter: aggregate,
    layout: {
      'text-field': ['match', ['get', 'precision'], 'city', 'CITY REF', 'AREA REF'],
      'text-font': ['Open Sans Bold'], 'text-size': 9, 'text-offset': [0, 2.8],
      'text-allow-overlap': true, 'text-ignore-placement': true,
    },
    paint: { 'text-color': referenceStroke, 'text-halo-color': '#171a18', 'text-halo-width': 1.5 },
  } as any);

  const approximate = ['all', ['!', ['has', 'cluster']], ['==', ['get', 'kind'], 'approximate']];
  map.addLayer({
    id: 'approximate-points', type: 'circle', source: 'locations', filter: approximate,
    paint: { 'circle-radius': 6, 'circle-color': '#d8c99b', 'circle-opacity': 0.88, 'circle-stroke-color': '#262820', 'circle-stroke-width': 2 },
  } as any);
  const sourceCoordinate = ['all', ['!', ['has', 'cluster']], ['==', ['get', 'kind'], 'source-coordinate']];
  map.addLayer({
    id: 'source-coordinate-points', type: 'circle', source: 'locations', filter: sourceCoordinate,
    paint: { 'circle-radius': 6.5, 'circle-color': '#d8c99b', 'circle-opacity': 0.94, 'circle-stroke-color': '#171a18', 'circle-stroke-width': 2.5 },
  } as any);
  const exact = ['all', ['!', ['has', 'cluster']], ['==', ['get', 'kind'], 'exact']];
  map.addLayer({
    id: 'exact-shadows', type: 'symbol', source: 'locations', filter: exact,
    layout: { 'icon-image': 'pin-shadow', 'icon-anchor': 'bottom', 'icon-size': 0.5, 'icon-allow-overlap': true, 'icon-ignore-placement': true },
  } as any);
  map.addLayer({
    id: 'exact-pins', type: 'symbol', source: 'locations', filter: exact,
    layout: { 'icon-image': ['get', 'icon'], 'icon-anchor': 'bottom', 'icon-size': 0.5, 'icon-allow-overlap': true, 'icon-ignore-placement': true },
  } as any);
}

/** Load only the legacy marker assets the fixture path needs. */
export async function loadJsonFallbackImages(map: MapLibreMap, baseUrl: string): Promise<void> {
  for (const color of new Set(Object.values(PIN_COLORS))) {
    const id = `pin-${color}`;
    if (!map.hasImage(id)) map.addImage(id, (await map.loadImage(`${baseUrl}marker-icon-2x-${color}.png`)).data);
  }
  if (!map.hasImage('pin-shadow')) map.addImage('pin-shadow', (await map.loadImage(`${baseUrl}marker-shadow.png`)).data);
}

export function setJsonFallbackData(map: MapLibreMap, data: JsonMapCollection): boolean {
  const source = map.getSource('locations') as GeoJSONSource | undefined;
  if (!source) return false;
  source.setData(data as any);
  return true;
}
