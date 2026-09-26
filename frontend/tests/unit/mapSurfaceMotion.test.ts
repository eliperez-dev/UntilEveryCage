import { describe, expect, it } from "vitest";
import { mvtClusterColor } from "../../src/design-lab/components/mapSurfaceMotion";

describe("MapSurface motion primitives", () => {
  it("uses the same density bands as the native MVT cluster symbols", () => {
    expect(mvtClusterColor(1)).toBe("#6ecc39b8");
    expect(mvtClusterColor(10)).toBe("#f0c20cb8");
    expect(mvtClusterColor(100)).toBe("#f18017b8");
  });
});
