import { describe, expect, it } from "vitest";
import {
  formatCameraCenter,
  projectWorldPosition,
} from "../../src/design-lab/components/worldLocatorProjection";

describe("world locator projection", () => {
  it("places the equator and Greenwich at the map center", () => {
    expect(projectWorldPosition(0, 0)).toMatchObject({ x: 180, y: 90 });
  });

  it("wraps longitude and clamps latitude", () => {
    expect(projectWorldPosition(100, 190)).toMatchObject({
      latitude: 90,
      longitude: -170,
      x: 10,
      y: 0,
    });
  });

  it("formats the camera center with hemispheres", () => {
    expect(formatCameraCenter(-42.123, 172.5)).toBe("42.12° S · 172.50° E");
    expect(formatCameraCenter(41.4273, -75.6514)).toBe(
      "41.43° N · 75.65° W",
    );
  });
});
