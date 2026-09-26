/**
 * Pure decisions for the MVT continuity/lineage controller.
 * Rendering remains in MapSurface because it owns the MapLibre instance and canvas.
 */

export type LineageCluster = Readonly<{
  featureKey?: string;
  parentKey?: string;
}>;

export function selectLineageChildren<T extends LineageCluster>(
  clusters: readonly T[],
  parentKey: string,
  limit = 8,
): readonly T[] {
  return clusters
    .filter((cluster) => cluster.parentKey === parentKey)
    .slice(0, limit);
}
