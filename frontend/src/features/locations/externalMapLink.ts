type PublicMapDestination = Readonly<{
  latitude?: number | null | undefined;
  longitude?: number | null | undefined;
  precision?: string | null | undefined;
  coordinatePrecision?: string | null | undefined;
  sourceLocationRole?: string | null | undefined;
}>;

/** A destination only: never include the visitor's location or an inferred point. */
export function externalMapLink(destination: PublicMapDestination): string | null {
  const { latitude, longitude, precision, coordinatePrecision, sourceLocationRole } = destination;
  if (typeof latitude !== 'number' || !Number.isFinite(latitude) || Math.abs(latitude) > 90 ||
      typeof longitude !== 'number' || !Number.isFinite(longitude) || Math.abs(longitude) > 180 ||
      !['source_reported', 'exact'].includes(precision ?? '') || sourceLocationRole ||
      /approx|city|coarse|postal|mail|locality|centroid/i.test(coordinatePrecision ?? '')) return null;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${latitude},${longitude}`)}`;
}
