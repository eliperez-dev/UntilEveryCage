import { TAXONOMY_PRIMARY_KEYS, isTaxonomyPrimaryKey } from '../../domain/taxonomy';
import type { AreaSummary, ViewportBounds } from '../../design-lab/contract';
import type { JsonMapCollection } from '../../design-lab/components/jsonMapFallback';

export function emptyAreaSummary(status: AreaSummary['status']): AreaSummary {
  return { status, total: 0, categories: TAXONOMY_PRIMARY_KEYS.map(key => ({ key, count: 0 })), sourceCount: 0,
    sourceReportedCount: 0, approximateCount: 0, bounds: null };
}

/** Uses original complete point features, never rendered clusters or a paginated list. */
export function summarizeMappedArea(collection: JsonMapCollection): AreaSummary {
  const counts = new Map(TAXONOMY_PRIMARY_KEYS.map(key => [key, 0]));
  const ids = new Set<string>();
  const sources = new Set<string>();
  let sourceReportedCount = 0, approximateCount = 0;
  let bounds: ViewportBounds | null = null;
  for (const feature of collection.features) {
    const id = feature.properties.facility_id ?? feature.properties.id ?? feature.id;
    const [longitude, latitude] = feature.geometry.coordinates;
    if (typeof id !== 'string' || ids.has(id) || !Number.isFinite(longitude) || !Number.isFinite(latitude)
      || Math.abs(longitude) > 180 || Math.abs(latitude) > 90) continue;
    ids.add(id);
    const rawCategory = feature.properties.category_key;
    const key = isTaxonomyPrimaryKey(rawCategory) ? rawCategory : 'unclassified';
    counts.set(key, counts.get(key)! + 1);
    if (typeof feature.properties.source_id === 'string') sources.add(feature.properties.source_id);
    if (feature.properties.precision === 'exact' || feature.properties.precision === 'source_reported') sourceReportedCount++;
    else approximateCount++;
    bounds = bounds ? { west: Math.min(bounds.west, longitude), east: Math.max(bounds.east, longitude),
      south: Math.min(bounds.south, latitude), north: Math.max(bounds.north, latitude) }
      : { west: longitude, east: longitude, south: latitude, north: latitude };
  }
  return { status: 'ready', total: ids.size, categories: TAXONOMY_PRIMARY_KEYS.map(key => ({ key, count: counts.get(key)! })),
    sourceCount: sources.size, sourceReportedCount, approximateCount, bounds };
}
