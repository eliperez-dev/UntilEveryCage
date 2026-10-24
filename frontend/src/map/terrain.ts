/** Public, keyless Terrarium DEM provider used only while the camera is tilted. */
export const TERRAIN_SOURCE_ID = 'mapterhorn-terrain';
export const TERRAIN_SOURCE = Object.freeze({
  type: 'raster-dem' as const,
  tiles: Object.freeze(['https://tiles.mapterhorn.com/{z}/{x}/{y}.webp']),
  tileSize: 512,
  encoding: 'terrarium' as const,
  attribution: '<a href="https://mapterhorn.com/attribution">© Mapterhorn</a>',
});
export const TERRAIN_EXAGGERATION = 1;
