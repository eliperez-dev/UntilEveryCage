export const DEFAULT_NEARBY_RADIUS_KM = 80.4672;
export type DeviceLocation = Readonly<{ latitude: number; longitude: number }>;

export function validDeviceLocation(value: DeviceLocation): boolean {
  return Number.isFinite(value.latitude) && Number.isFinite(value.longitude)
    && Math.abs(value.latitude) <= 90 && Math.abs(value.longitude) <= 180;
}

/** One explicit permission request. Its result and cancellation state stay in memory. */
export function requestDeviceLocation(signal?: AbortSignal): Promise<DeviceLocation> {
  return new Promise((resolve, reject) => {
    const abortError = () => new DOMException('Location request was cancelled.', 'AbortError');
    if (signal?.aborted) { reject(abortError()); return; }
    if (typeof navigator === 'undefined' || !navigator.geolocation) { reject(new Error('Your location is unavailable.')); return; }
    let settled = false;
    const finish = (action: () => void) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener('abort', abort);
      action();
    };
    const abort = () => finish(() => reject(abortError()));
    signal?.addEventListener('abort', abort, { once: true });
    try {
      navigator.geolocation.getCurrentPosition(position => {
        const value = { latitude: position.coords.latitude, longitude: position.coords.longitude };
        finish(() => validDeviceLocation(value) ? resolve(value) : reject(new Error('Your location is unavailable.')));
      }, error => finish(() => reject(new Error(error.code === 1 ? 'Location permission was denied.'
        : error.code === 3 ? 'Location request timed out.' : 'Your location is unavailable.'))),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 });
    } catch { finish(() => reject(new Error('Your location is unavailable.'))); }
  });
}

/** Radius overview usable even before any records arrive, including empty nearby searches. */
export function nearbyOverviewZoom(radiusKm: number, latitude: number): number {
  const latitudeScale = Math.max(.15, Math.cos(latitude * Math.PI / 180));
  return Math.max(2, Math.min(12, Math.log2(40075 * latitudeScale / (radiusKm * 4))));
}

/** Camera bounds may wrap beyond180 degrees; the live scope remains a geodesic radius. */
export function nearbyCameraBounds(location: DeviceLocation, radiusKm: number): [[number, number], [number, number]] {
  const latitudeSpan = radiusKm / 111.195;
  const longitudeSpan = Math.min(180, latitudeSpan / Math.max(.01, Math.cos(location.latitude * Math.PI / 180)));
  return [[location.longitude - longitudeSpan, Math.max(-85, location.latitude - latitudeSpan)],
    [location.longitude + longitudeSpan, Math.min(85, location.latitude + latitudeSpan)]];
}
