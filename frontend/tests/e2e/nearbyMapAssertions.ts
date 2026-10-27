import { expect, type Page } from '@playwright/test';

/** An explicit nearby search fits its radius, rather than zooming onto the device. */
export async function expectNearbyScope(page: Page, center: { latitude: number; longitude: number }) {
  await expect.poll(() => page.evaluate(async point => {
    const map = (window as any).__UEC_LOCAL_PREVIEW_MAP__;
    const source = map?.getSource('search-radius');
    if (!source || map.isMoving()) return false;
    const data = await source.getData();
    const edge = data.features?.[0]?.geometry?.coordinates?.[0]?.[0];
    if (!edge) return false;
    const radians = (degrees: number) => degrees * Math.PI / 180;
    const deltaLat = radians(edge[1] - point.latitude), deltaLon = radians(edge[0] - point.longitude);
    const haversine = Math.sin(deltaLat / 2) ** 2 + Math.cos(radians(point.latitude))
      * Math.cos(radians(edge[1])) * Math.sin(deltaLon / 2) ** 2;
    const distanceKm = 6371 * 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
    const pixel = map.project([point.longitude, point.latitude]);
    const canvas = map.getCanvas().getBoundingClientRect();
    return Math.abs(distanceKm - 80.4672) < 1 && map.getZoom() < 12
      && pixel.x >= 0 && pixel.x <= canvas.width && pixel.y >= 0 && pixel.y <= canvas.height;
  }, center), { timeout: 20_000 }).toBe(true);
}
