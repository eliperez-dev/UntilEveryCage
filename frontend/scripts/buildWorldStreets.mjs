// Bounded extraction from Protomaps' explicitly downloadable ODbL database.
// https://docs.protomaps.com/basemaps/downloads
import { gunzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { Buffer } from 'node:buffer';
import { URL } from 'node:url';
const url = 'https://build.protomaps.com/20261025.pmtiles';
const directory = new URL('../public/world-baseline/', import.meta.url);
await mkdir(directory, { recursive: true });
async function read(start, length) {
  const response = await fetch(url, { headers: { Range: `bytes=${start}-${start + length - 1}` } });
  if (response.status !== 206) throw new Error(`Expected bounded range: ${response.status}`);
  const data = new Uint8Array(await response.arrayBuffer());
  if (data.length !== length) throw new Error('Incomplete bounded range');
  return data;
}
const first = await read(0, 16384), header = new DataView(first.buffer);
const uint64 = offset => Number(header.getBigUint64(offset, true));
function decode(data) {
  const bytes = first[97] === 2 ? gunzipSync(data) : data;
  let position = 0;
  function variable() { let value = 0, shift = 0, byte; do { byte = bytes[position++]; value += (byte & 127) * 2 ** shift; shift += 7; } while (byte & 128); return value; }
  const count = variable(), entries = []; let id = 0;
  for (let i = 0; i < count; i++) { id += variable(); entries.push({ id }); }
  for (const entry of entries) entry.run = variable();
  for (const entry of entries) entry.length = variable();
  for (let i = 0; i < count; i++) { const offset = variable(); entries[i].offset = offset === 0 && i > 0 ? entries[i - 1].offset + entries[i - 1].length : offset - 1; }
  return entries;
}
const selected = [];
async function walk(entries) {
  for (const entry of entries) {
    if (entry.id >= 1365) break;
    if (entry.run) selected.push(entry);
    else await walk(decode(await read(uint64(40) + entry.offset, entry.length)));
  }
}
await walk(decode(first.slice(uint64(8), uint64(8) + uint64(16))));
const length = Math.max(...selected.map(entry => entry.offset + entry.length));
if (length > 32 * 1048576) throw new Error('Low-zoom extraction exceeds its budget');
const payload = await read(uint64(56), length);
const chunks = Array.from({ length: 6 }, () => []), sizes = Array(6).fill(0), index = Array(1365), positions = new Map();
for (const entry of selected) {
  const key = `${entry.offset}:${entry.length}`;
  let position = positions.get(key);
  if (!position) {
    const chunk = Math.floor(Math.log(3 * entry.id + 1) / Math.log(4));
    position = [chunk, sizes[chunk], entry.length]; positions.set(key, position);
    chunks[chunk].push(payload.slice(entry.offset, entry.offset + entry.length)); sizes[chunk] += entry.length;
  }
  for (let id = entry.id; id < Math.min(1365, entry.id + entry.run); id++) index[id] = position;
}
const assets = [];
for (let i = 0; i < chunks.length; i++) {
  const bytes = Buffer.concat(chunks[i]), sha256 = createHash('sha256').update(bytes).digest('hex');
  const file = `streets-z${i}.${sha256.slice(0, 12)}.bin`;
  await writeFile(new URL(file, directory), bytes); assets.push({ file, bytes: bytes.length, sha256, zoom: i });
}
await writeFile(new URL('../src/map/assets/worldStreetsManifest.json', import.meta.url), JSON.stringify({ source: url, license: 'ODbL 1.0 database subset', assets, tiles: index }));
console.log(JSON.stringify({ assets, totalBytes: sizes.reduce((a, b) => a + b) }));
