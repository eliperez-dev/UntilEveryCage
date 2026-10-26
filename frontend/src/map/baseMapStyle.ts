import worldLandRaw from './assets/ne_110m_land.geojson?raw';
import { tileCacheUrl } from './tileCache';
import { registerTileCacheProtocol } from './tileCacheProtocol';
import { registerWorldBaselineProtocol } from './worldBaseline';

// Natural Earth v5.1.2, 1:110m land, public domain. Bundled locally so the
// world outline remains visible beneath provider tiles without prefetching.
// https://www.naturalearthdata.com/about/terms-of-use/
// https://github.com/nvkelso/natural-earth-vector/blob/v5.1.2/geojson/ne_110m_land.geojson
// Original SHA-256: 9e0729ee253ca7d7a5c4ae9395fb1902264c5377c52e224d13dd85010e2835d9
const worldLand: unknown = JSON.parse(worldLandRaw);

export type BasemapKind = 'vector' | 'muted' | 'satellite';
export const BASE_RASTER_FADE_MS = 180;

/** Desaturate the existing OpenStreetMap raster without changing its provider. */
export function baseRasterPaint(basemap: BasemapKind): Record<string, number> {
  return basemap === 'muted'
    ? { 'raster-saturation': -1, 'raster-contrast': 0.12, 'raster-brightness-min': 0.08, 'raster-brightness-max': 0.92, 'raster-fade-duration': BASE_RASTER_FADE_MS }
    : { 'raster-saturation': 0, 'raster-contrast': 0, 'raster-brightness-min': 0, 'raster-brightness-max': 1, 'raster-fade-duration': BASE_RASTER_FADE_MS };
}

/** Existing local-preview basemap style, shared without importing design-lab code into production. */
export function createBaseStyle(basemap: BasemapKind, options: { includeTransport?: boolean } = {}): Record<string, unknown> {
  registerTileCacheProtocol();
  registerWorldBaselineProtocol();
  const satellite = basemap === 'satellite';
  const includeTransport = options.includeTransport ?? true;
  const base = basemap === 'satellite'
    ? { type: 'raster', tiles: [tileCacheUrl('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}')], tileSize: 256, attribution: 'Tiles © Esri' }
    : { type: 'raster', tiles: [tileCacheUrl('https://tile.openstreetmap.org/{z}/{x}/{y}.png')], tileSize: 256, attribution: '© OpenStreetMap contributors' };
  const sources = {
    'world-land': { type: 'geojson', data: worldLand, maxzoom: 4, attribution: 'Natural Earth' },
    'world-streets': { type: 'vector', tiles: ['uec-world://streets/{z}/{x}/{y}'], maxzoom: 5, attribution: '<a href="https://openstreetmap.org/copyright">© OpenStreetMap</a> · Protomaps' },
    'world-satellite': { type: 'raster', tiles: ['uec-world://satellite/{z}/{x}/{y}'], tileSize: 256, maxzoom: 5, attribution: 'NASA Blue Marble (2004)' },
    base,
    ...(includeTransport ? { transport: { type: 'raster', tiles: [tileCacheUrl('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}')], tileSize: 256, attribution: 'Transportation © Esri' } } : {}),
  };
  return {
    version: 8,
    sources,
    layers: [
      { id: 'world-ocean', type: 'background', paint: { 'background-color': satellite ? '#9daaa8' : '#aad3df' } },
      { id: 'world-land', type: 'fill', source: 'world-land', paint: { 'fill-color': satellite ? '#93947e' : '#f2efe9', 'fill-antialias': false } },
      { id: 'world-streets-land', maxzoom: 6, type: 'fill', source: 'world-streets', 'source-layer': 'earth', layout: { visibility: satellite ? 'none' : 'visible' }, paint: { 'fill-color': '#f2efe9' } },
      { id: 'world-streets-forest', maxzoom: 6, type: 'fill', source: 'world-streets', 'source-layer': 'landcover', filter: ['==', ['get', 'kind'], 'forest'], layout: { visibility: satellite ? 'none' : 'visible' }, paint: { 'fill-color': '#d8e8cf' } },
      { id: 'world-streets-water', maxzoom: 6, type: 'fill', source: 'world-streets', 'source-layer': 'water', layout: { visibility: satellite ? 'none' : 'visible' }, paint: { 'fill-color': '#aad3df' } },
      { id: 'world-streets-roads', maxzoom: 6, type: 'line', source: 'world-streets', 'source-layer': 'roads', layout: { visibility: satellite ? 'none' : 'visible' }, paint: { 'line-color': '#dba56b', 'line-width': 0.8 } },
      { id: 'world-streets-borders', maxzoom: 6, type: 'line', source: 'world-streets', 'source-layer': 'boundaries', layout: { visibility: satellite ? 'none' : 'visible' }, paint: { 'line-color': '#b3a4b8', 'line-width': 0.7, 'line-dasharray': [3, 2] } },
      { id: 'world-streets-labels', maxzoom: 6, type: 'symbol', source: 'world-streets', 'source-layer': 'places', layout: { visibility: satellite ? 'none' : 'visible', 'text-field': ['coalesce', ['get', 'name:en'], ['get', 'name:latin'], ''], 'text-font': ['sans-serif'], 'text-size': 12, 'text-padding': 8 }, paint: { 'text-color': '#4b4b4b', 'text-halo-color': '#f2efe9', 'text-halo-width': 1.3 } },
      // Source detail remains capped at z5. Keep its coarse imagery underneath
      // detailed provider tiles when zooming, including terrain's unfaded swaps.
      { id: 'world-satellite', type: 'raster', source: 'world-satellite', layout: { visibility: satellite ? 'visible' : 'none' }, paint: { 'raster-fade-duration': 0 } },
      { id: 'base', type: 'raster', source: 'base', paint: baseRasterPaint(basemap) },
      ...(includeTransport ? [{ id: 'transport', type: 'raster', source: 'transport', paint: { 'raster-opacity': satellite ? 0.72 : 0, 'raster-fade-duration': 0 } }] : []),
    ],
  };
}
