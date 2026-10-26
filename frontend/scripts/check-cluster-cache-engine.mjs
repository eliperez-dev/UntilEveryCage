import { readFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const nativeRequire = createRequire(import.meta.resolve('maplibre-gl'));
for (const [name, expected] of Object.entries({ 'maplibre-gl': '6.11.0', '@maplibre/geojson-vt': '6.1.1', kdbush: '4.1.0' })) {
  // MapLibre is import-only; inspect the native worker's dependency resolution
  // as well as the codec's, including a possible nested installation.
  const entries = [fileURLToPath(import.meta.resolve(name))];
  if (name !== 'maplibre-gl') entries.push(nativeRequire.resolve(name), require.resolve(name));
  for (const entry of entries) {
    let directory = dirname(entry);
    let actual;
    while (directory !== dirname(directory)) {
      const file = join(directory, 'package.json');
      if (existsSync(file)) {
        const metadata = JSON.parse(readFileSync(file, 'utf8'));
        if (metadata.name === name) { actual = metadata.version; break; }
      }
      directory = dirname(directory);
    }
    if (actual !== expected) throw new Error(`Built-index cache adapter requires ${name}@${expected}; found ${actual ?? 'unavailable'}. Review the codec and worker adapter before upgrading.`);
  }
}
const { GeoJSONSource } = await import('maplibre-gl');
if (typeof GeoJSONSource?.prototype?._getLoadGeoJSONParameters !== 'function') {
  throw new Error('The public map transport requires the pinned GeoJSONSource parameter boundary. Review the adapter before upgrading.');
}
console.log('Persistent map cache engine versions verified.');
