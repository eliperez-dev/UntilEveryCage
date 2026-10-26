import type { JsonMapCollection } from './jsonMapFallback';

/** V1 enabled clustering for the filtered population, never viewport density. */
export const CLUSTERING_POPULATION_THRESHOLD = 2800;

export function representedMappedCount(collection: JsonMapCollection): number {
  return collection.features.reduce((total, feature) => {
    const weight = Number(feature.properties.weight ?? 1);
    return total + (Number.isFinite(weight) && weight > 0 ? weight : 1);
  }, 0);
}

export function clusterFilteredPopulation(collection: JsonMapCollection, override: boolean | null = null): boolean {
  return override ?? representedMappedCount(collection) >= CLUSTERING_POPULATION_THRESHOLD;
}

/** IDs come from the complete, identity-validated public matches endpoint. */
export function maskPublicMapMatches(
  collection: JsonMapCollection,
  ids: ReadonlySet<string> | null,
  status: 'idle' | 'loading' | 'ready' | 'error',
): JsonMapCollection {
  if (status === 'loading' || status === 'error') return { ...collection, features: [] };
  if (ids === null) return collection;
  return { ...collection, features: collection.features.filter(feature => {
    const id = feature.properties.facility_id ?? feature.properties.id ?? feature.id;
    return typeof id === 'string' && ids.has(id);
  }) };
}

/** A layout change only resizes the existing renderer; it does not touch data. */
export function resizeWorkspaceMap(
  map: { resize(): unknown; jumpTo(camera: { center: [number, number] }): unknown },
  activeSelectionCenter: [number, number] | null,
  flying: boolean,
): void {
  map.resize();
  // Only an explicit selection flight owns a focus. A selected shared URL or
  // a manually panned camera must not be recentered when the panel resizes.
  if (activeSelectionCenter && !flying) map.jumpTo({ center: activeSelectionCenter });
}
