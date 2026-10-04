export type ClaimedPoint = Readonly<{ latitude: number; longitude: number }>;

/** Normalize a map click into a finite WGS84 pair with stable UI precision. */
export function normalizeClaimedPoint(latitude: number, longitude: number): ClaimedPoint | null {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || latitude < -90 || latitude > 90) return null;
  const normalizedLongitude = ((longitude + 180) % 360 + 360) % 360 - 180;
  return { latitude: Number(latitude.toFixed(6)), longitude: Number(normalizedLongitude.toFixed(6)) };
}
