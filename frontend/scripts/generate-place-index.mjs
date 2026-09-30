/**
 * Reduce Natural Earth 10m populated places to the public map-navigation fields.
 *
 * Source: https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_10m_populated_places_simple.geojson
 * Natural Earth 5.1.2; public domain: https://www.naturalearthdata.com/about/terms-of-use/
 * Input SHA-256 (2026-09-27): fd3fa867a320cbd5c5b6bb5bc550afeec2939fb2cef688e508007282a55ac42f
 *
 * Usage: node scripts/generate-place-index.mjs <source.geojson>
 * The raw source is deliberately kept outside the repository.
 */

import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';

const EXPECTED_SHA256 = 'fd3fa867a320cbd5c5b6bb5bc550afeec2939fb2cef688e508007282a55ac42f';
const inputPath = process.argv[2];

if (!inputPath) {
  throw new Error('Provide the Natural Earth source GeoJSON path.');
}

const bytes = await readFile(resolve(inputPath));
const checksum = createHash('sha256').update(bytes).digest('hex');
if (checksum !== EXPECTED_SHA256) {
  throw new Error(`Natural Earth source checksum mismatch: ${checksum}`);
}

const source = JSON.parse(bytes.toString('utf8'));
if (source.type !== 'FeatureCollection' || !Array.isArray(source.features)) {
  throw new Error('Expected a Natural Earth GeoJSON FeatureCollection.');
}

const rows = source.features.map(({ properties, geometry }) => {
  const coordinates = geometry?.coordinates;
  const longitude = coordinates?.[0];
  const latitude = coordinates?.[1];

  if (
    geometry?.type !== 'Point' ||
    !Number.isFinite(longitude) ||
    !Number.isFinite(latitude) ||
    longitude < -180 || longitude > 180 ||
    latitude < -90 || latitude > 90 ||
    !properties?.name || !properties?.adm0name ||
    !Number.isInteger(properties?.ne_id)
  ) {
    throw new Error('Natural Earth source contains an invalid place row.');
  }

  // [Natural Earth ID, name, admin-1, country, longitude, latitude, population rank]
  return [
    properties.ne_id,
    properties.name,
    properties.adm1name || '',
    properties.adm0name,
    longitude,
    latitude,
    Number.isFinite(properties.rank_max) ? properties.rank_max : 0,
  ];
});

rows.sort((a, b) => a[0] - b[0]);
const outputPath = resolve('src/features/placeSearch/places.json');
await writeFile(outputPath, `${JSON.stringify(rows)}\n`, 'utf8');
console.log(`Wrote ${rows.length} Natural Earth places to ${outputPath}`);
