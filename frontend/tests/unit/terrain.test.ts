import { describe, expect, it } from 'vitest';
import { TERRAIN_EXAGGERATION, TERRAIN_SOURCE, TERRAIN_SOURCE_ID } from '../../src/map/terrain';

describe('keyless public terrain source contract', () => {
  it('uses licensed keyless Terrarium tiles, precise attribution, and natural relief scale', () => {
    expect(TERRAIN_SOURCE_ID).toBe('mapterhorn-terrain');
    expect(TERRAIN_SOURCE).toMatchObject({
      type: 'raster-dem',
      tiles: ['https://tiles.mapterhorn.com/{z}/{x}/{y}.webp'],
      tileSize: 512,
      encoding: 'terrarium',
      attribution: '<a href="https://mapterhorn.com/attribution">© Mapterhorn</a>',
    });
    expect(TERRAIN_EXAGGERATION).toBe(1);
  });
});
