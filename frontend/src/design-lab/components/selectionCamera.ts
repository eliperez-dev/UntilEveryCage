import { TERRAIN_SOURCE_ID } from '../../map/terrain';

export type CameraLodSource = { calculateTileZoom?: (requestedCenterZoom: number, ...distances: number[]) => number };

/** Keep source detail tied to camera zoom, independent of bearing or pitch. */
export function useCameraZoomLod(source: CameraLodSource): void {
  // Public Source.calculateTileZoom is also used by MapLibre's LOD setter.
  // Apply to facility and basemap sources; DEM retains adaptive terrain detail.
  source.calculateTileZoom = requestedCenterZoom => requestedCenterZoom;
}

type TerrainSelectionMap = {
  getTerrain(): unknown;
  getSource(id: string): unknown;
  isSourceLoaded(id: string): boolean;
  queryTerrainElevation(center: [number, number]): number | null;
  getCenterElevation(): number;
  getCenter(): { lng: number; lat: number };
  jumpTo(camera: { center: [number, number]; elevation: number }): unknown;
};

/** Commit the target height through the camera API after its DEM has settled. */
export function settleTerrainSelection(map: TerrainSelectionMap, center: [number, number]): boolean {
  if (!map.getTerrain()) return true;
  if (!map.getSource(TERRAIN_SOURCE_ID) || !map.isSourceLoaded(TERRAIN_SOURCE_ID)) return false;
  const elevation = map.queryTerrainElevation(center);
  if (elevation === null || !Number.isFinite(elevation)) return false;
  const current = map.getCenter();
  if (Math.abs(map.getCenterElevation() - elevation) > .01 || Math.abs(current.lng - center[0]) > 1e-8 || Math.abs(current.lat - center[1]) > 1e-8) {
    // jumpTo updates the requested camera copy as well as the rendered one.
    map.jumpTo({ center, elevation });
  }
  return true;
}
