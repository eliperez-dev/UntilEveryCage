/** Public Terrarium DEM: loaded on first tilt, then retained through overhead views. */
export const TERRAIN_SOURCE_ID = 'mapterhorn-terrain';
export const TERRAIN_SOURCE = Object.freeze({
  type: 'raster-dem' as const,
  tiles: Object.freeze(['https://tiles.mapterhorn.com/{z}/{x}/{y}.webp']),
  tileSize: 512,
  encoding: 'terrarium' as const,
  attribution: '<a href="https://mapterhorn.com/attribution">© Mapterhorn</a>',
});
export const TERRAIN_EXAGGERATION = 1;
