import type { Map as MapLibreMap } from 'maplibre-gl';
import type { JsonMapCollection } from './jsonMapFallback';

/** The real-preview feed and its references share one native Supercluster index. */
export function addRealPreviewMapLayers(map: MapLibreMap, data: JsonMapCollection): void {
  if (map.getSource('locations')) return;
  map.addSource('locations', {
    type: 'geojson',
    data,
    cluster: true,
    clusterRadius: 50,
    clusterMaxZoom: 14,
    clusterProperties: { representedCount: ['+', ['get', 'weight']] },
  } as any);

  const unclustered = ['!', ['has', 'cluster']];
  const representedCount = ['get', 'representedCount'];
  map.addLayer({
    id: 'clusters', type: 'symbol', source: 'locations', filter: ['has', 'cluster'],
    layout: {
      'icon-image': ['step', representedCount, 'cluster-low', 10, 'cluster-mid', 100, 'cluster-high'],
      'icon-size': 1, 'icon-allow-overlap': true, 'icon-ignore-placement': true,
      'text-field': ['to-string', representedCount], 'text-font': ['Open Sans Bold'], 'text-size': 12,
      'text-allow-overlap': true, 'text-ignore-placement': true,
    },
    paint: { 'text-color': '#172019' },
  } as any);

  const reference = ['all', unclustered, ['==', ['get', 'kind'], 'reference']];
  const weight = ['get', 'weight'];
  map.addLayer({
    id: 'aggregate-outer', type: 'circle', source: 'locations', filter: reference,
    paint: { 'circle-color': '#15252c', 'circle-radius': 18, 'circle-opacity': 0.96, 'circle-stroke-color': '#86aeca', 'circle-stroke-width': 3 },
  } as any);
  map.addLayer({
    id: 'aggregate-count', type: 'symbol', source: 'locations', filter: reference,
    layout: { 'text-field': ['to-string', weight], 'text-font': ['Open Sans Bold'], 'text-size': 12 },
    paint: { 'text-color': '#f1efe8' },
  } as any);
  map.addLayer({
    id: 'aggregate-kind', type: 'symbol', source: 'locations', filter: reference,
    layout: { 'text-field': ['match', ['get', 'precision'], 'city', 'CITY REF', 'city_reference_approximate', 'CITY REF', 'AREA REF'], 'text-font': ['Open Sans Bold'], 'text-size': 9, 'text-offset': [0, 2.8], 'text-allow-overlap': true, 'text-ignore-placement': true },
    paint: { 'text-color': '#86aeca', 'text-halo-color': '#171a18', 'text-halo-width': 1.5 },
  } as any);

  const coordinate = ['all', unclustered, ['==', ['get', 'kind'], 'source-coordinate']];
  map.addLayer({
    id: 'source-coordinate-points', type: 'circle', source: 'locations', filter: coordinate,
    paint: { 'circle-radius': 6.5, 'circle-color': '#d8c99b', 'circle-opacity': 0.94, 'circle-stroke-color': '#171a18', 'circle-stroke-width': 2.5 },
  } as any);
}

export function setRealPreviewMapData(map: MapLibreMap, data: JsonMapCollection): boolean {
  const source = map.getSource('locations') as any;
  if (!source?.setData) return false;
  source.setData(data);
  return true;
}
