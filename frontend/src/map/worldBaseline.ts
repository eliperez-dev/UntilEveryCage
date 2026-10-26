import { addProtocol } from 'maplibre-gl';
import streetsRaw from './assets/worldStreetsManifest.json?raw';
import satelliteRaw from './assets/worldSatelliteManifest.json?raw';
import { getTileCacheDiagnostics, subscribeTileCacheDiagnostics } from './tileCache';

type Asset = { file: string; bytes: number; sha256: string; zoom: number };
type Manifest = { assets: Asset[]; tiles: [number, number, number][] };
const manifests: Record<'streets' | 'satellite', Manifest> = { streets: JSON.parse(streetsRaw), satellite: JSON.parse(satelliteRaw) };
const assets = [...manifests.streets.assets, ...manifests.satellite.assets];
export const WORLD_BASELINE_CACHE_NAME = 'uec-world-baseline-v1';
const TTL = 30 * 86400_000;
const mobile = typeof matchMedia !== 'undefined' && matchMedia('(max-width: 700px)').matches;
export type WorldBaselineSettings = { enabled: boolean; maxZoom: number; maxBytes: number };
export type WorldBaselineDiagnostics = { status: 'idle' | 'warming' | 'ready' | 'partial' | 'paused' | 'unavailable'; bytes: number; hits: number; requests: number; readyChunks: number; totalChunks: number; maxZoom: number };
const defaults: Readonly<WorldBaselineSettings> = Object.freeze({ enabled: true, maxZoom: mobile ? 4 : 5, maxBytes: (mobile ? 12 : 24) * 1048576 });
let settings = { ...defaults };
let diagnostic: WorldBaselineDiagnostics = { status: 'idle', bytes: 0, hits: 0, requests: 0, readyChunks: 0, totalChunks: 12, maxZoom: settings.maxZoom };
const listeners = new Set<(value: WorldBaselineDiagnostics) => void>();
const loaded = new Map<string, Uint8Array>();
const lookups = new Map<string, Promise<Uint8Array | undefined>>();
let generation = 0;
let warmer: AbortController | undefined;
let registered = false;
const urlFor = (asset: Asset) => new URL(`${import.meta.env.BASE_URL}world-baseline/${asset.file}`, location.href).href;
const eligible = () => settings.enabled && getTileCacheDiagnostics().persistenceAllowed;
function plan() {
  let bytes = 0;
  return [...assets].sort((a, b) => a.zoom - b.zoom).filter(asset => {
    if (asset.zoom > settings.maxZoom || bytes + asset.bytes > settings.maxBytes) return false;
    bytes += asset.bytes; return true;
  });
}
function emit(status = diagnostic.status) {
  const desired = plan();
  diagnostic = { ...diagnostic, status, bytes: [...loaded.values()].reduce((sum, value) => sum + value.byteLength, 0),
    readyChunks: desired.filter(asset => loaded.has(asset.file)).length, totalChunks: desired.length, maxZoom: settings.maxZoom };
  for (const listener of listeners) listener({ ...diagnostic });
}
export function getWorldBaselineSettings(): WorldBaselineSettings { return { ...settings }; }
export function getWorldBaselineDiagnostics(): WorldBaselineDiagnostics { return { ...diagnostic }; }
export function subscribeWorldBaselineDiagnostics(listener: (value: WorldBaselineDiagnostics) => void): () => void {
  listeners.add(listener); listener(getWorldBaselineDiagnostics()); return () => { listeners.delete(listener); };
}
export function updateWorldBaselineSettings(patch: Partial<WorldBaselineSettings>): WorldBaselineSettings {
  cancelWorldBaselineWarmup();
  const bounded = (value: number | undefined, previous: number, low: number, high: number) => value !== undefined && Number.isFinite(value) ? Math.round(Math.min(high, Math.max(low, value))) : previous;
  settings = { enabled: patch.enabled ?? settings.enabled, maxZoom: bounded(patch.maxZoom, settings.maxZoom, 0, 5), maxBytes: bounded(patch.maxBytes, settings.maxBytes, 8 * 1048576, 40 * 1048576) };
  void trim(); emit('idle'); return getWorldBaselineSettings();
}
export function resetWorldBaselineSettings(): WorldBaselineSettings { return updateWorldBaselineSettings(defaults); }
export function cancelWorldBaselineWarmup(): void { generation++; warmer?.abort(); warmer = undefined; emit('paused'); }
async function sha(data: Uint8Array) {
  const digest = await crypto.subtle.digest('SHA-256', new Uint8Array(data));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}
async function lookup(asset: Asset): Promise<Uint8Array | undefined> {
  if (loaded.has(asset.file)) return loaded.get(asset.file);
  if (!eligible() || !plan().some(candidate => candidate.file === asset.file) || !globalThis.caches) return undefined;
  if (lookups.has(asset.file)) return lookups.get(asset.file);
  const epoch = generation;
  const pending = (async () => {
    try {
      const cache = await caches.open(WORLD_BASELINE_CACHE_NAME), url = urlFor(asset), response = await cache.match(url);
      if (!response) return undefined;
      const date = Number(response.headers.get('x-uec-world-stored'));
      const data = new Uint8Array(await response.arrayBuffer());
      if (!Number.isFinite(date) || date <= 0 || date + TTL <= Date.now() || data.byteLength !== asset.bytes || await sha(data) !== asset.sha256) { await cache.delete(url); return undefined; }
      if (epoch !== generation || !eligible()) return undefined;
      loaded.set(asset.file, data); diagnostic.hits++; emit(); return data;
    } catch { return undefined; }
  })();
  lookups.set(asset.file, pending);
  void pending.finally(() => { if (lookups.get(asset.file) === pending) lookups.delete(asset.file); });
  return pending;
}
async function trim() {
  const allowed = new Set(plan().map(asset => asset.file));
  for (const file of loaded.keys()) if (!allowed.has(file)) loaded.delete(file);
  try {
    const cache = await caches.open(WORLD_BASELINE_CACHE_NAME);
    for (const key of await cache.keys()) if (!assets.some(asset => allowed.has(asset.file) && key.url === urlFor(asset))) await cache.delete(key);
  } catch { /* Storage is optional. */ }
  emit();
}
export async function clearWorldBaselineCache(): Promise<void> {
  cancelWorldBaselineWarmup(); loaded.clear(); lookups.clear();
  try { await caches.delete(WORLD_BASELINE_CACHE_NAME); } catch { /* Memory remains usable without storage. */ }
  emit('idle');
}
async function persist(asset: Asset, data: Uint8Array, epoch: number): Promise<void> {
  try {
    const cache = await caches.open(WORLD_BASELINE_CACHE_NAME), url = urlFor(asset);
    const stored = await cache.match(url), date = Number(stored?.headers.get('x-uec-world-stored'));
    if (stored && Number.isFinite(date) && date > 0 && date + TTL > Date.now()) return;
    if (!eligible() || epoch !== generation) return;
    await cache.put(url, new Response(new Uint8Array(data), { headers: { 'x-uec-world-stored': String(Date.now()), 'content-type': 'application/octet-stream' } }));
    // A newer warmer may use the same immutable asset. An older write must
    // not delete that valid entry merely because the settings changed.
    if (!eligible() || !plan().some(current => current.file === asset.file)) await cache.delete(url);
  } catch { /* A blocked disk cache does not discard the usable RAM copy. */ }
}
export async function warmWorldBaseline(): Promise<void> {
  const saveData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData;
  if (!eligible() || saveData || document.hidden) { emit('paused'); return; }
  if (warmer) return;
  const controller = new AbortController(), epoch = generation;
  warmer = controller; emit('warming');
  try {
    await trim();
    for (const asset of plan()) {
      controller.signal.throwIfAborted();
      const cached = await lookup(asset);
      // A canceled warmer may have filled RAM before its disk write finished.
      if (cached) { await persist(asset, cached, epoch); continue; }
      if (!eligible() || epoch !== generation) break;
      diagnostic.requests++; emit('warming');
      const response = await fetch(urlFor(asset), { signal: controller.signal, cache: 'default', credentials: 'omit' });
      if (!response.ok) throw new Error('World baseline unavailable');
      const data = new Uint8Array(await response.arrayBuffer());
      if (data.byteLength !== asset.bytes || await sha(data) !== asset.sha256) throw new Error('World baseline integrity failed');
      if (!eligible() || epoch !== generation) break;
      loaded.set(asset.file, data);
      await persist(asset, data, epoch);
      emit('warming');
    }
    if (epoch === generation) emit(plan().every(asset => loaded.has(asset.file)) ? 'ready' : 'partial');
  } catch { if (epoch === generation) emit(controller.signal.aborted ? 'paused' : 'unavailable'); }
  finally { if (warmer === controller) warmer = undefined; }
}

/** PMTiles v3 cumulative Hilbert index, for the bounded z0-5 local tile table. */
export function worldTileId(z: number, x: number, y: number): number {
  if (!Number.isInteger(z) || z < 0 || z > 5 || !Number.isInteger(x) || !Number.isInteger(y) || x < 0 || y < 0 || x >= 2 ** z || y >= 2 ** z) throw new Error('Invalid local world tile');
  const width = 2 ** z; let id = (width * width - 1) / 3;
  for (let step = width / 2; step >= 1; step /= 2) {
    const rx = (x & step) !== 0 ? 1 : 0, ry = (y & step) !== 0 ? 1 : 0;
    id += step * step * ((3 * rx) ^ ry);
    if (!ry) { if (rx) { x = step - 1 - x; y = step - 1 - y; } [x, y] = [y, x]; }
  }
  return id;
}
async function tile(url: string, signal: AbortSignal): Promise<{ data: ArrayBuffer; cacheControl: string }> {
  const match = /^uec-world:\/\/(streets|satellite)\/(\d+)\/(\d+)\/(\d+)$/.exec(url);
  if (!match) throw new Error('Unsupported local world tile URL');
  const kind = match[1] as 'streets' | 'satellite', manifest = manifests[kind];
  const position = manifest.tiles[worldTileId(Number(match[2]), Number(match[3]), Number(match[4]))];
  if (!position) throw new Error('Local world tile unavailable');
  const [chunk, offset, length] = position, asset = manifest.assets[chunk]!;
  const whole = loaded.get(asset.file) ?? await lookup(asset);
  signal.throwIfAborted();
  let data: Uint8Array;
  if (whole) { diagnostic.hits++; data = whole.slice(offset, offset + length); }
  else {
    diagnostic.requests++;
    const response = await fetch(urlFor(asset), { signal, cache: 'default', credentials: 'omit', headers: { Range: `bytes=${offset}-${offset + length - 1}` } });
    if (!response.ok) throw new Error('Local world tile unavailable');
    const responseData = new Uint8Array(await response.arrayBuffer());
    if (response.status === 206 && responseData.byteLength === length) data = responseData;
    else if (response.status === 200 && responseData.byteLength === asset.bytes) data = responseData.slice(offset, offset + length);
    else throw new Error('Local world tile range was invalid');
  }
  if (kind === 'streets') data = new Uint8Array(await new Response(new Blob([new Uint8Array(data)]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
  signal.throwIfAborted(); emit();
  return { data: data.buffer as ArrayBuffer, cacheControl: 'max-age=31536000' };
}
export function registerWorldBaselineProtocol(): void {
  if (registered) return;
  registered = true; addProtocol('uec-world', (request, controller) => tile(request.url, controller.signal));
  subscribeTileCacheDiagnostics(value => { if (!value.persistenceAllowed && warmer) cancelWorldBaselineWarmup(); });
}
type StyleMap = { getLayer(id: string): unknown; setLayoutProperty(id: string, name: string, value: string): unknown; setPaintProperty(id: string, name: string, value: number): unknown };
export const WORLD_STREETS_LAYERS = ['world-streets-land', 'world-streets-forest', 'world-streets-water', 'world-streets-roads', 'world-streets-borders', 'world-streets-labels'] as const;
export function applyWorldBaselineBasemap(map: unknown, basemap: 'vector' | 'muted' | 'satellite'): void {
  const instance = map as StyleMap;
  for (const id of WORLD_STREETS_LAYERS) if (instance.getLayer(id)) instance.setLayoutProperty(id, 'visibility', basemap === 'satellite' ? 'none' : 'visible');
  if (instance.getLayer('world-satellite')) instance.setLayoutProperty('world-satellite', 'visibility', basemap === 'satellite' ? 'visible' : 'none');
}
export function applyWorldBaselineOpacity(map: unknown, opacity: number): void {
  const instance = map as StyleMap, value = Math.min(1, Math.max(0, opacity));
  for (const id of ['world-land', ...WORLD_STREETS_LAYERS, 'world-satellite']) if (instance.getLayer(id)) {
    const property = id === 'world-satellite' ? 'raster-opacity' : id === 'world-streets-roads' || id === 'world-streets-borders' ? 'line-opacity' : id === 'world-streets-labels' ? 'text-opacity' : 'fill-opacity';
    instance.setPaintProperty(id, property, value);
  }
}
