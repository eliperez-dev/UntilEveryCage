import { describe, expect, it } from "vitest";
import { MvtMotionController } from "../../src/design-lab/components/mvtMotionController";

describe("MVT click motion", () => {
  it("does not change native layer paint during ordinary controller cleanup", () => {
    const paints: string[] = [];
    const controller = new MvtMotionController({ getMap: () => fakeMap(paints) as any });

    controller.cancel();

    expect(paints).toEqual([]);
  });

  it("leaves no native paint changes when an expansion cannot resolve children", () => {
    const paints: string[] = [];
    const controller = new MvtMotionController({ getMap: () => fakeMap(paints) as any });

    controller.queueExpansion({
      parentKey: "parent",
      longitude: 12,
      latitude: 44,
      count: 7,
      targetZoom: 4,
    });
    controller.playExpansion();

    expect(paints).toEqual([]);
  });
});

function fakeMap(paints: string[]) {
  return {
    getLayer: () => ({}),
    queryRenderedFeatures: () => [],
    project: () => ({ x: 10, y: 10 }),
    setPaintProperty: (layer: string, property: string) => paints.push(`${layer}:${property}`),
    areTilesLoaded: () => true,
    isSourceLoaded: () => true,
    getZoom: () => 4,
    setFilter: () => {},
  };
}
