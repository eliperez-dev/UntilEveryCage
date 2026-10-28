import type { Map as MapLibreMap } from 'maplibre-gl';

/** Version-locked to the engine checked by check-cluster-cache-engine.mjs.
 * Painter.render uploads feature state while preparing the current tiles.
 * Reuse that placed scene without Map.redraw's second input-task/placement
 * pass and synthetic zero timestamp inside the same browser frame.
 */
export function repaintPlacedScene(map: MapLibreMap): void {
  const native = map as unknown as {
    style?: unknown;
    painter?: {
      options?: unknown;
      context: { setDirty(): void };
      setBaseState(): void;
      render(style: unknown, options: unknown): void;
    };
  };
  const painter = native.painter;
  if (native.style && painter?.options) {
    painter.context.setDirty();
    painter.setBaseState();
    painter.render(native.style, painter.options);
  } else map.redraw();
}
