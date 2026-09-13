import type { Map as LeafletMap, Marker } from 'leaflet';
import type { MapAdapter } from './MapAdapter';
import type { DisplayFeature } from './mapProjection';
type MarkerFactory = (feature: DisplayFeature, map: LeafletMap) => Marker;
export class LeafletMapAdapter implements MapAdapter {
  #map: LeafletMap | null = null; #markers = new Map<string, Marker>(); #disposed = false; #makeMarker: MarkerFactory | null = null;
  async mount(container: HTMLElement): Promise<void> { const leaflet = await import('leaflet'); if (this.#disposed) return; this.#makeMarker = (feature, map) => leaflet.marker([feature.lat, feature.lon], { title: feature.label }).addTo(map); this.#map = leaflet.map(container, { attributionControl: false, zoomControl: true }).setView([55, 10], 6); this.#map.getContainer().style.background = '#ded8cc'; }
  update(features: readonly DisplayFeature[], selectedId: string | null): void { if (!this.#map || !this.#makeMarker) return; const active = new Set(features.map((feature) => feature.id)); for (const [id, marker] of this.#markers) { if (!active.has(id)) { marker.remove(); this.#markers.delete(id); } } for (const feature of features) { const marker = this.#markers.get(feature.id) ?? this.#makeMarker(feature, this.#map); this.#markers.set(feature.id, marker); marker.setOpacity(selectedId === null || selectedId === feature.id ? 1 : 0.55); } }
  destroy(): void { this.#disposed = true; for (const marker of this.#markers.values()) marker.remove(); this.#markers.clear(); this.#map?.remove(); this.#map = null; this.#makeMarker = null; }
}
