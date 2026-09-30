/** Equirectangular coordinates for the locally bundled Natural Earth outline. */
export function projectWorldPosition(latitude: number, longitude: number) {
  const safeLatitude = Number.isFinite(latitude)
    ? Math.max(-90, Math.min(90, latitude))
    : 0;
  const safeLongitude = Number.isFinite(longitude)
    ? ((longitude + 180) % 360 + 360) % 360 - 180
    : 0;

  return {
    x: safeLongitude + 180,
    y: 90 - safeLatitude,
    latitude: safeLatitude,
    longitude: safeLongitude,
  };
}

/** The label describes the map camera, not a record's location precision. */
export function formatCameraCenter(latitude: number, longitude: number) {
  const position = projectWorldPosition(latitude, longitude);
  const northSouth = position.latitude < 0 ? "S" : "N";
  const eastWest = position.longitude < 0 ? "W" : "E";
  return `${Math.abs(position.latitude).toFixed(2)}° ${northSouth} · ${Math.abs(position.longitude).toFixed(2)}° ${eastWest}`;
}
