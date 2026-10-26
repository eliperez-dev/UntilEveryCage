/** MapLibre 6.11 has constructor cache limits but no live public setter.
 * Keep the version-sensitive access in one guarded compatibility boundary.
 * TileManager.updateCacheSize immediately evicts excess out-of-view tiles;
 * no source is reloaded and the current viewport remains intact.
 */
export function updateMapTileMemoryCache(map: unknown, requested: number): boolean {
  if (!map || !Number.isFinite(requested)) return false;
  const instance = map as {
    _maxTileCacheSize?: number; _camera?: { transform?: unknown };
    style?: { tileManagers?: Record<string, { _maxTileCacheSize?: number; updateCacheSize?: (transform: unknown) => void }> };
  };
  if (typeof instance._maxTileCacheSize !== 'number' && instance._maxTileCacheSize !== null) return false;
  const managers = instance.style?.tileManagers;
  const transform = instance._camera?.transform;
  if (!managers || !transform) return false;
  const limit = Math.round(Math.max(32, Math.min(256, requested)));
  instance._maxTileCacheSize = limit;
  for (const manager of Object.values(managers)) {
    if (typeof manager.updateCacheSize !== 'function' || !('_maxTileCacheSize' in manager)) continue;
    manager._maxTileCacheSize = limit;
    manager.updateCacheSize(transform);
  }
  return true;
}
