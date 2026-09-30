import { describe, expect, it } from 'vitest';
import { searchPlaces } from '../../src/features/placeSearch/placeSearch';
import placeRows from '../../src/features/placeSearch/places.json';

describe('local place search', () => {
  it('finds San Diego as a city destination with source coordinates and context', () => {
    const sanDiego = searchPlaces('San Diego')[0];
    expect(sanDiego).toMatchObject({
      kind: 'place',
      label: 'San Diego, California, United States',
      longitude: -117.150881,
      latitude: 32.718914,
      source: 'Natural Earth',
      precision: 'city-centre',
    });
  });

  it('disambiguates names using their administrative region and country', () => {
    const springfields = searchPlaces('Springfield', 10);
    expect(springfields.length).toBeGreaterThan(1);
    expect(new Set(springfields.map(place => place.label)).size).toBe(springfields.length);
    expect(springfields.every(place => place.label.endsWith('United States'))).toBe(true);
    expect(searchPlaces('Springfield Illinois')[0]?.label).toBe('Springfield, Illinois, United States');
  });

  it('supports diacritic-insensitive search and bounds the result count', () => {
    expect(searchPlaces('sao paulo')[0]?.name).toBe('São Paulo');
    expect(searchPlaces('san', 3)).toHaveLength(3);
  });

  it('does not search empty or one-character queries', () => {
    expect(searchPlaces('')).toEqual([]);
    expect(searchPlaces(' S ')).toEqual([]);
    expect(searchPlaces('San Diego', 0)).toEqual([]);
  });

  it('contains valid map coordinates and no facility-record fields', () => {
    expect(placeRows).toHaveLength(7342);
    expect(placeRows.every((row) =>
      Number.isFinite(row[4]) && row[4] >= -180 && row[4] <= 180 &&
      Number.isFinite(row[5]) && row[5] >= -90 && row[5] <= 90,
    )).toBe(true);

    const place = searchPlaces('San Diego')[0];
    expect(place).not.toHaveProperty('facilityId');
    expect(place).not.toHaveProperty('address');
    expect(place).not.toHaveProperty('reviewStatus');
  });
});
