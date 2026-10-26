import { addProtocol } from 'maplibre-gl';
import { loadViewedTile } from './tileCache';

let registered = false;
export function registerTileCacheProtocol(): void {
  if (registered) return;
  registered = true;
  addProtocol('uec-tile', (request, controller) => loadViewedTile(request.url, controller.signal));
}
