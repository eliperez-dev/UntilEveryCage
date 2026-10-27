import { describe, expect, it } from 'vitest';
import { externalMapLink } from '../../src/features/locations/externalMapLink';

describe('public external map destination', () => {
  it('opens only the public destination with no route origin or record text', () => {
    const link = new URL(externalMapLink({latitude:12.5, longitude:-45.25, precision:'source_reported'})!);
    expect(link.origin + link.pathname).toBe('https://www.google.com/maps/search/');
    expect([...link.searchParams.entries()]).toEqual([['api','1'],['query','12.5,-45.25']]);
    expect(externalMapLink({latitude:0, longitude:0, precision:'exact'})).not.toBeNull();
  });
  it('never sends coarse, missing, mailing or invalid destinations to another map', () => {
    for (const precision of ['approximate','city','coarse','unmapped',null]) expect(externalMapLink({latitude:12,longitude:30,precision})).toBeNull();
    for (const coordinatePrecision of ['city-centroid','approximate','postal','mailing-locality']) expect(externalMapLink({latitude:12,longitude:30,precision:'source_reported',coordinatePrecision})).toBeNull();
    expect(externalMapLink({latitude:12,longitude:30,precision:'source_reported',sourceLocationRole:'aphis_mailing_locality'})).toBeNull();
    for (const latitude of [null,NaN,Infinity,91,-91]) expect(externalMapLink({latitude,longitude:30,precision:'exact'})).toBeNull();
    for (const longitude of [null,NaN,Infinity,181,-181]) expect(externalMapLink({latitude:12,longitude,precision:'exact'})).toBeNull();
  });
});
