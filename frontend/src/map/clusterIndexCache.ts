import type { PublicReleaseIdentity } from '../api/PublicReleaseRepository';
import { decodeStoredClusterIndex, encodeStoredClusterIndex, storedClusterIndexBytes, PackedIndexError } from './packedClusterIndex';
import type { ClusterIndexSnapshot } from './clusterIndexCodec';

export const INDEX_CACHE_ENGINE = 'maplibre-6.11.0/geojson-vt-6.1.1/kdbush-4.1.0';
export const INDEX_CACHE_DB = 'uec-public-cluster-index-v1';
export const INDEX_CACHE_CHANNEL = 'uec-public-cluster-index-diagnostics-v1';
export const INDEX_CACHE_FIELD = 'uec_public_index';
export type IndexCacheIdentity = PublicReleaseIdentity & { profile: 'official'; session: string; maxMiB: number };
export type IndexCacheDiagnostic = {
  session: string;
  state: 'lookup' | 'building' | 'stored' | 'restored' | 'unavailable';
  builds: number;
  restores: number;
  reason?: IndexCacheFailureReason;
  storedBytes?: number;
  timings?: IndexCacheTimings;
  startedAtEpochMs?: number;
  reportedAtEpochMs?: number;
};
export type IndexCacheTimings = { transportEncodeMs: number; transportParseMs: number; hashMs: number; databaseMs: number; inflateMs: number; parseMs: number; validationMs: number; reconstructionMs: number; nativeLoadMs: number; totalMs: number };
export type IndexCacheFailureReason = 'cache-limit' | 'compression-unavailable' | 'storage-unavailable' | 'invalid-snapshot' | 'cleared-during-build';
export function indexCacheFailureReason(error: unknown): IndexCacheFailureReason {
  return error instanceof PackedIndexError ? error.reason : 'storage-unavailable';
}

export function publicIndexIdentity(value: unknown): IndexCacheIdentity | null {
  if (!value || typeof value !== 'object') return null;
  const item = value as Record<string, unknown>;
  if (item.profile !== 'official' || typeof item.releaseId !== 'string' || !/^[A-Za-z0-9._-]{1,160}$/.test(item.releaseId)
    || typeof item.manifestSha256 !== 'string' || !/^[a-f0-9]{64}$/.test(item.manifestSha256)
    || !Number.isSafeInteger(item.suppressionGeneration) || Number(item.suppressionGeneration) < 0
    || typeof item.session !== 'string' || !/^[a-zA-Z0-9-]{1,80}$/.test(item.session)) return null;
  return { profile: 'official', releaseId: item.releaseId, manifestSha256: item.manifestSha256,
    suppressionGeneration: Number(item.suppressionGeneration), session: item.session,
    maxMiB: typeof item.maxMiB === 'number' && Number.isFinite(item.maxMiB) ? Math.max(8, Math.min(64, item.maxMiB)) : 64 };
}

/** No query text, scopes or device camera are part of the persisted identity. */
export async function clusterIndexKey(identity: IndexCacheIdentity, features: unknown, options: unknown, properties: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify([INDEX_CACHE_ENGINE, identity.profile, identity.releaseId,
    identity.manifestSha256, identity.suppressionGeneration, options, properties, features]));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, '0')).join('');
}

type StoredIndex = { key: string; engine: string; snapshot: unknown; bytes: number };
const STORE = 'index';
const SLOT = 'active';
const MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024;

async function openIndexDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!globalThis.indexedDB) { reject(new Error('Storage unavailable')); return; }
    let settled = false;
    const timeout = setTimeout(() => { settled = true; reject(new Error('Storage timed out')); }, 1500);
    const request = indexedDB.open(INDEX_CACHE_DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onerror = () => { clearTimeout(timeout); settled = true; reject(request.error); };
    request.onblocked = () => { clearTimeout(timeout); settled = true; reject(new Error('Storage blocked')); };
    request.onsuccess = () => { clearTimeout(timeout); if (settled) request.result.close(); else { settled = true; resolve(request.result); } };
  });
}

export async function readClusterIndex(key: string, maxMiB = 64, currentInput?: readonly unknown[]): Promise<{ snapshot: unknown | null; epoch: number; storedBytes?: number; timings?: { databaseMs: number; inflateMs: number; parseMs: number } }> {
  const started = performance.now();
  const db = await openIndexDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE, 'readonly');
      const request = transaction.objectStore(STORE).get(SLOT);
      const epoch = transaction.objectStore(STORE).get('epoch');
      transaction.oncomplete = async () => {
        const item = request.result as StoredIndex | undefined;
        try {
          const eligible = item?.key === key && item.engine === INDEX_CACHE_ENGINE && Number.isFinite(item.bytes) && item.bytes > 0 && item.bytes <= maxMiB * 1024 * 1024;
          const timings = { databaseMs: performance.now() - started, inflateMs: 0, parseMs: 0 };
          const snapshot = eligible ? await decodeStoredClusterIndex(item.snapshot, maxMiB * 1048576, value => Object.assign(timings, value), currentInput) : null;
          resolve({ snapshot, timings, epoch: typeof epoch.result === 'number' ? epoch.result : 0, ...(eligible ? { storedBytes: item.bytes } : {}) });
        } catch (error) { reject(error); }
      };
      request.onerror = () => reject(request.error);
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally { db.close(); }
}

export async function writeClusterIndex(key: string, snapshot: ClusterIndexSnapshot, epoch: number, maxMiB = 64, signal?: AbortSignal, onStoredBytes?: (bytes: number) => void, currentInput?: readonly unknown[]): Promise<boolean> {
  // Finish the immutable capture synchronously before yielding to another load.
  const packed = await encodeStoredClusterIndex(snapshot, currentInput);
  // Bound the persisted payload before opening a transaction. Array buffers are
  // counted separately because JSON represents them as empty objects.
  const bytes = storedClusterIndexBytes(packed);
  if (bytes > Math.min(MAX_SNAPSHOT_BYTES, maxMiB * 1024 * 1024)) throw new PackedIndexError('cache-limit');
  onStoredBytes?.(bytes);
  const db = await openIndexDatabase();
  try {
    return await new Promise<boolean>((resolve, reject) => {
      const transaction = db.transaction(STORE, 'readwrite');
      const store = transaction.objectStore(STORE);
      const current = store.get('epoch');
      let stored = false;
      current.onsuccess = () => {
        if (!signal?.aborted && (current.result ?? 0) === epoch) {
          store.put({ key, engine: INDEX_CACHE_ENGINE, snapshot: packed, bytes } satisfies StoredIndex, SLOT);
          stored = true;
        }
      };
      transaction.oncomplete = () => resolve(stored);
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally { db.close(); }
}

export async function clearClusterIndexCache(): Promise<void> {
  if (!globalThis.indexedDB) return;
  const db = await openIndexDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(STORE, 'readwrite');
      const store = transaction.objectStore(STORE);
      const current = store.get('epoch');
      current.onsuccess = () => { store.delete(SLOT); store.put(Number(current.result ?? 0) + 1, 'epoch'); };
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally { db.close(); }
}

export async function trimClusterIndexCache(maxMiB: number): Promise<void> {
  const db = await openIndexDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(STORE, 'readwrite');
      const store = transaction.objectStore(STORE);
      const active = store.get(SLOT), epoch = store.get('epoch');
      epoch.onsuccess = () => {
        const entry = active.result as StoredIndex | undefined;
        if (entry && (!Number.isFinite(entry.bytes) || entry.bytes < 1 || entry.bytes > maxMiB * 1048576)) store.delete(SLOT);
        // Cancel any pending writer that captured the previous budget.
        store.put(Number(epoch.result ?? 0) + 1, 'epoch');
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally { db.close(); }
}
