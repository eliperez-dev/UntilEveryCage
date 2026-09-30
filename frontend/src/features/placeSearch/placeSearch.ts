import placeRows from './places.json';

// This module is intended for a dynamic import when Map Search opens. Its
// public-domain gazetteer is not part of the initial map bundle.
type PlaceRow = [
  id: number,
  name: string,
  admin1: string,
  country: string,
  longitude: number,
  latitude: number,
  rank: number,
];

export interface PlaceSuggestion {
  id: string;
  kind: 'place';
  name: string;
  admin1: string;
  country: string;
  label: string;
  longitude: number;
  latitude: number;
  rank: number;
  precision: 'city-centre';
  source: 'Natural Earth';
}

function normalize(value: string): string {
  return value.normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

interface IndexedPlace {
  place: PlaceSuggestion;
  normalizedName: string;
  normalizedLabel: string;
}

const places: IndexedPlace[] = (placeRows as PlaceRow[]).map((row) => {
  const [sourceId, name, admin1, rawCountry, longitude, latitude, rank] = row;
  const country = rawCountry === 'United States of America' ? 'United States' : rawCountry;
  const label = [name, admin1 && admin1 !== name ? admin1 : '', country]
    .filter(Boolean).join(', ');

  return {
    place: {
      id: `natural-earth:${sourceId}`,
      kind: 'place',
      name,
      admin1,
      country,
      label,
      longitude,
      latitude,
      rank,
      precision: 'city-centre',
      source: 'Natural Earth',
    },
    normalizedName: normalize(name),
    normalizedLabel: normalize(label),
  };
});

function matchTier(normalizedName: string, normalizedLabel: string, normalizedQuery: string): number {
  if (normalizedName === normalizedQuery) return 0;
  if (normalizedName.startsWith(normalizedQuery)) return 1;
  if (normalizedLabel.startsWith(normalizedQuery)) return 2;
  if (normalizedName.split(' ').some(word => word.startsWith(normalizedQuery))) return 3;
  if (normalizedQuery.split(' ').every(token => normalizedLabel.includes(token))) return 4;
  if (normalizedName.includes(normalizedQuery)) return 5;
  return Infinity;
}

/**
 * Search a bounded set of city destinations. These are Natural Earth place
 * points, not geocoded addresses or verified facility coordinates.
 */
export function searchPlaces(query: string, limit = 5): PlaceSuggestion[] {
  const normalizedQuery = normalize(query);
  if (normalizedQuery.length < 2 || limit <= 0) return [];

  const matches: Array<{ tier: number; place: PlaceSuggestion }> = [];
  for (const { place, normalizedName, normalizedLabel } of places) {
    const tier = matchTier(normalizedName, normalizedLabel, normalizedQuery);
    if (!Number.isFinite(tier)) continue;
    matches.push({ tier, place });
  }

  matches.sort((a, b) => a.tier - b.tier || b.place.rank - a.place.rank || a.place.label.localeCompare(b.place.label));
  return matches.slice(0, Math.min(20, Math.floor(limit))).map(({ place }) => place);
}
