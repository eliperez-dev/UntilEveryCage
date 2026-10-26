type SelectionOverlayMap = {
  getSource(id: string): unknown;
  getLayer(id: string): unknown;
};

/** Raster/terrain requests do not prevent an existing selection overlay accepting data or paint. */
export function syncSelectionOverlayWhenReady(map: SelectionOverlayMap | undefined, sync: () => void): void {
  if (map?.getSource('locations') && map.getLayer('aggregate-outer')) sync();
}
