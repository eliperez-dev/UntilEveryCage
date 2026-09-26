/**
 * Draws only verified, click-triggered MVT cluster lineage motion.
 *
 * Normal camera movement belongs to MapLibre. This controller never snapshots,
 * hides, filters, or redraws ordinary map tiles: that work made panning slower
 * than the native renderer.
 */
import type { Map as MapLibreMap } from "maplibre-gl";
import { selectLineageChildren } from "./mvtLineage";
import {
  drawMotionDot,
  mvtClusterColor,
  resizeMotionCanvas,
  type ClusterMotion,
  type MotionDot,
} from "./mapSurfaceMotion";

type Expansion = Readonly<{
  parentKey: string;
  longitude: number;
  latitude: number;
  count: number;
  targetZoom: number;
  expiresAt: number;
}>;
type ExpansionHistory = Readonly<{ parentKey: string; childKeys: readonly string[] }>;

export type MvtMotionControllerOptions = Readonly<{
  getMap: () => MapLibreMap | undefined;
  reducedMotion?: () => boolean;
}>;

/** Canvas renderer for a small, genuine parent/child split or reverse join. */
export class MvtMotionController {
  private canvas: HTMLCanvasElement | undefined;
  private frame: number | undefined;
  private expansionTimer: ReturnType<typeof setTimeout> | undefined;
  private motion: ClusterMotion | undefined;
  private pendingExpansion: Expansion | undefined;
  private hiddenKeys: readonly string[] = [];
  private history: ExpansionHistory | undefined;
  private pendingJoin: Readonly<{ startZoom: number; children: readonly MotionDot[] }> | undefined;

  constructor(private readonly options: MvtMotionControllerOptions) {}

  attach(parent: HTMLElement): void {
    this.canvas = document.createElement("canvas");
    this.canvas.className = "cluster-motion";
    this.canvas.setAttribute("aria-hidden", "true");
    Object.assign(this.canvas.style, { position: "absolute", inset: "0", zIndex: "3", width: "100%", height: "100%", pointerEvents: "none" });
    parent.append(this.canvas);
  }

  dispose(): void {
    this.cancel();
    this.canvas?.remove();
    this.canvas = undefined;
  }

  /** Cancels only active click motion; native MVT symbols always stay visible. */
  cancel(): void {
    if (this.frame) cancelAnimationFrame(this.frame);
    if (this.expansionTimer) clearTimeout(this.expansionTimer);
    this.frame = this.expansionTimer = undefined;
    this.motion = this.pendingExpansion = undefined;
    this.restoreHiddenKeys();
    this.clearCanvas();
  }

  clearLineage(): void {
    this.history = undefined;
    this.pendingJoin = undefined;
    this.pendingExpansion = undefined;
  }

  queueExpansion(value: Omit<Expansion, "expiresAt">): void {
    this.pendingExpansion = { ...value, expiresAt: performance.now() + 900 };
  }

  playExpansion(): void {
    const map = this.options.getMap(), expansion = this.pendingExpansion;
    if (!map || !expansion || this.isReduced()) return;
    if (map.getZoom() < expansion.targetZoom - 0.2 || !map.areTilesLoaded() || !map.isSourceLoaded("preview-mvt")) return;
    const children = selectLineageChildren(this.snapshot(), expansion.parentKey);
    if (children.length < 2) {
      if (performance.now() < expansion.expiresAt) this.expansionTimer = setTimeout(() => this.playExpansion(), 48);
      else this.pendingExpansion = undefined;
      return;
    }
    this.pendingExpansion = undefined;
    this.hiddenKeys = children.map((child) => child.featureKey!).filter(Boolean);
    this.setClusterFilter(this.hiddenKeys);
    this.history = { parentKey: expansion.parentKey, childKeys: this.hiddenKeys };
    const origin = map.project([expansion.longitude, expansion.latitude]);
    this.motion = { startedAt: performance.now(), duration: 320, origin: { x: origin.x, y: origin.y, count: expansion.count, color: mvtClusterColor(expansion.count) }, children, direction: "split" };
    this.scheduleDraw();
  }

  prepareJoin(startZoom: number): void {
    if (this.isReduced() || !this.history) return;
    const children = this.snapshot().filter((dot) => this.history!.childKeys.includes(dot.featureKey ?? ""));
    if (children.length >= 2) this.pendingJoin = { startZoom, children };
  }

  playJoin(): void {
    const map = this.options.getMap(), join = this.pendingJoin, history = this.history;
    if (!map || !join || !history || map.getZoom() >= join.startZoom - 0.15 || !map.areTilesLoaded() || !map.isSourceLoaded("preview-mvt")) return;
    const parent = this.snapshot().find((dot) => dot.featureKey === history.parentKey);
    if (!parent) { this.pendingJoin = undefined; return; }
    this.pendingJoin = undefined;
    this.hiddenKeys = [history.parentKey];
    this.setClusterFilter(this.hiddenKeys);
    this.motion = { startedAt: performance.now(), duration: 280, origin: parent, children: join.children, direction: "join" };
    this.scheduleDraw();
  }

  private isReduced(): boolean { return this.options.reducedMotion?.() ?? false; }
  private snapshot(): readonly MotionDot[] {
    const map = this.options.getMap();
    if (!map?.getLayer("mvt-clusters")) return [];
    const seen = new Set<string>(), dots: MotionDot[] = [];
    for (const feature of map.queryRenderedFeatures({ layers: ["mvt-clusters"] }) as any[]) {
      const coordinates = feature.geometry?.coordinates, count = Number(feature.properties?.count), key = String(feature.properties?.feature_key ?? "");
      if (!Array.isArray(coordinates) || coordinates.length !== 2 || !Number.isFinite(count) || !key || seen.has(key)) continue;
      const longitude = Number(coordinates[0]), latitude = Number(coordinates[1]);
      if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) continue;
      seen.add(key); const point = map.project([longitude, latitude]);
      dots.push({ x: point.x, y: point.y, longitude, latitude, count, color: mvtClusterColor(count), featureKey: key, parentKey: typeof feature.properties?.parent_key === "string" ? feature.properties.parent_key : undefined });
    }
    return dots;
  }
  private setClusterFilter(hidden: readonly string[]): void {
    this.options.getMap()?.setFilter("mvt-clusters", ["all", ["==", ["get", "kind"], "cluster"], ["!", ["in", ["get", "feature_key"], ["literal", hidden]]]] as any);
  }
  private restoreHiddenKeys(): void { if (this.hiddenKeys.length) this.setClusterFilter([]); this.hiddenKeys = []; }
  private scheduleDraw(): void { if (!this.frame) this.frame = requestAnimationFrame(() => this.draw()); }
  private clearCanvas(): void { const canvas = this.canvas; canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height); }
  private draw(): void {
    this.frame = undefined;
    const canvas = this.canvas, map = this.options.getMap(), motion = this.motion;
    if (!canvas || !map || !motion) return;
    const rect = canvas.getBoundingClientRect(), context = resizeMotionCanvas(canvas, rect.width, rect.height, window.devicePixelRatio || 1);
    if (!context) return;
    context.clearRect(0, 0, rect.width, rect.height);
    const progress = Math.min(1, (performance.now() - motion.startedAt) / motion.duration), ease = 1 - Math.pow(1 - progress, 3);
    if (motion.direction === "join") {
      for (const child of motion.children) { const point = child.longitude === undefined || child.latitude === undefined ? child : map.project([child.longitude, child.latitude]); drawMotionDot(context, { ...child, x: point.x, y: point.y }, 1 - ease, .68 + ease * .32); }
      drawMotionDot(context, motion.origin, ease, 1 + ease * .14);
    } else {
      drawMotionDot(context, motion.origin, 1 - ease, 1 + ease * .14);
      for (const child of motion.children) drawMotionDot(context, { ...child, x: motion.origin.x + (child.x - motion.origin.x) * ease, y: motion.origin.y + (child.y - motion.origin.y) * ease }, ease, .68 + ease * .32);
    }
    if (progress < 1) { this.scheduleDraw(); return; }
    this.motion = undefined; this.restoreHiddenKeys(); this.clearCanvas();
  }
}
