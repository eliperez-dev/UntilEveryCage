export type BasemapKind = 'vector' | 'muted' | 'satellite';

/** Desaturate the existing OpenStreetMap raster without changing its provider. */
export function baseRasterPaint(basemap: BasemapKind): Record<string, number> {
  return basemap === 'muted'
    ? { 'raster-saturation': -1, 'raster-contrast': 0.12, 'raster-brightness-min': 0.08, 'raster-brightness-max': 0.92 }
    : { 'raster-saturation': 0, 'raster-contrast': 0, 'raster-brightness-min': 0, 'raster-brightness-max': 1 };
}

/** Existing local-preview basemap style, shared without importing design-lab code into production. */
export function createBaseStyle(basemap: BasemapKind, options: { includeTransport?: boolean } = {}): Record<string, unknown> {
  const satellite = basemap === 'satellite';
  const includeTransport = options.includeTransport ?? true;
  const base = basemap === 'satellite'
    ? { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, attribution: 'Tiles © Esri' }
    : { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, attribution: '© OpenStreetMap contributors' };
  return {
    version: 8,
    sources: satellite || includeTransport ? {
      base,
      ...(includeTransport ? { transport: { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, attribution: 'Transportation © Esri' } } : {}),
    } : { base },
    layers: includeTransport
      ? [
          { id: 'base', type: 'raster', source: 'base', paint: baseRasterPaint(basemap) },
          { id: 'transport', type: 'raster', source: 'transport', paint: { 'raster-opacity': satellite ? 0.72 : 0 } },
        ]
      : [{ id: 'base', type: 'raster', source: 'base', paint: baseRasterPaint(basemap) }],
  };
}
