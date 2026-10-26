import { describe, expect, it, vi } from 'vitest';
import { settleTerrainSelection, useCameraZoomLod, type CameraLodSource } from '../../src/design-lab/components/selectionCamera';

describe('geographic selection camera', () => {
  it('uses the camera zoom at every tile distance and camera angle', () => {
    const source: CameraLodSource = {};
    useCameraZoomLod(source);
    for (const distances of [[1, 1, 1, 45], [100, 200, 400, 45], [900, 1, 50, 60]]) {
      expect(source.calculateTileZoom?.(8.3, ...distances)).toBe(8.3);
      expect(source.calculateTileZoom?.(9, ...distances)).toBe(9);
    }
  });
  it('waits for target terrain and corrects stale flight height without changing rotation or zoom', () => {
    let ready = false;
    const map = { getTerrain: () => ({}), getSource: () => ({}), isSourceLoaded: () => ready,
      queryTerrainElevation: () => 1000, getCenterElevation: () => 0, getCenter: () => ({ lng: 4.45, lat: 50.95 }), jumpTo: vi.fn() };
    expect(settleTerrainSelection(map, [4.45, 50.95])).toBe(false); expect(map.jumpTo).not.toHaveBeenCalled();
    ready = true;
    expect(settleTerrainSelection(map, [4.45, 50.95])).toBe(true);
    expect(map.jumpTo).toHaveBeenCalledOnce();
    expect(map.jumpTo).toHaveBeenCalledWith({ center: [4.45, 50.95], elevation: 1000 });
  });
  it('does not move an already grounded camera or a flat map', () => {
    const map = { getTerrain: () => ({}), getSource: () => ({}), isSourceLoaded: () => true,
      queryTerrainElevation: () => -200, getCenterElevation: () => -200, getCenter: () => ({ lng: 4.45, lat: 50.95 }), jumpTo: vi.fn() };
    expect(settleTerrainSelection(map, [4.45, 50.95])).toBe(true); expect(map.jumpTo).not.toHaveBeenCalled();
    expect(settleTerrainSelection({ ...map, getTerrain: () => null }, [4.45, 50.95])).toBe(true);
    expect(map.jumpTo).not.toHaveBeenCalled();
  });
});
