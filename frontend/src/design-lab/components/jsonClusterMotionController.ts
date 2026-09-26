/**
 * Owns the bounded canvas transition used only by the JSON fixture fallback.
 *
 * The real-preview MVT path uses MvtMotionController instead. This controller
 * never changes clustered data; it only bridges an already-requested camera
 * move with a short, capped visual fan-out.
 */
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import {
  drawMotionDot,
  resizeMotionCanvas,
  type ClusterMotion,
} from "./mapSurfaceMotion";

type Options = Readonly<{
  getMap: () => MapLibreMap | undefined;
  reducedMotion: () => boolean;
}>;

export class JsonClusterMotionController {
  private canvas: HTMLCanvasElement | undefined;
  private frame: number | undefined;
  private fadeTimer: ReturnType<typeof setTimeout> | undefined;
  private generation = 0;
  private motion: ClusterMotion | undefined;
  private pendingExpansion: ClusterMotion | undefined;
  private activeExpansionToken: number | undefined;
  private nextExpansionToken = 0;

  constructor(private readonly options: Options) {}

  attach(parent: HTMLElement): void {
    this.canvas = document.createElement("canvas");
    this.canvas.className = "cluster-motion";
    this.canvas.setAttribute("aria-hidden", "true");
    Object.assign(this.canvas.style, {
      position: "absolute",
      inset: "0",
      zIndex: "3",
      width: "100%",
      height: "100%",
      pointerEvents: "none",
    });
    parent.append(this.canvas);
  }

  dispose(): void {
    this.cancel();
    this.canvas?.remove();
    this.canvas = undefined;
  }

  onZoomStart(event: { originalEvent?: unknown } | undefined): void {
    if (this.activeExpansionToken !== undefined && !event?.originalEvent) {
      const motion = this.pendingExpansion;
      if (motion) {
        this.motion = { ...motion, startedAt: performance.now() };
        this.pendingExpansion = undefined;
        this.scheduleDraw();
      }
      return;
    }
    this.cancel();
    this.showAtomicTransition();
  }

  armExpansion(map: MapLibreMap): number {
    const token = ++this.nextExpansionToken;
    this.activeExpansionToken = token;
    map.once("moveend", () => {
      if (this.activeExpansionToken === token) {
        this.activeExpansionToken = undefined;
        this.pendingExpansion = undefined;
      }
    });
    return token;
  }

  playExpansion(feature: any, clusterId: number): void {
    const map = this.options.getMap();
    if (!map || this.options.reducedMotion()) return;
    const generation = this.generation;
    const source = map.getSource("locations") as GeoJSONSource | undefined;
    source?.getClusterChildren(clusterId).then((children) => {
      if (
        !this.options.getMap() ||
        generation !== this.generation ||
        children.length < 2 ||
        children.length > 8
      )
        return;
      const originPoint = map.project(feature.geometry.coordinates);
      const origin = {
        x: originPoint.x,
        y: originPoint.y,
        count: Number(feature.properties?.representedCount ?? feature.properties?.point_count ?? 0),
        color: "#f0c20c",
      };
      const targets = children.map((child: any, index) => {
        const point = map.project(child.geometry.coordinates);
        return {
          x: point.x,
          y: point.y,
          count: Number(child.properties?.representedCount ?? child.properties?.point_count ?? 1),
          color: index % 2 ? "#f0c20c" : "#6ecc39",
        };
      });
      this.cancel(true);
      if (generation !== this.generation - 1) return;
      this.motion = {
        startedAt: performance.now(),
        duration: 360,
        origin,
        children: targets,
      };
      this.pendingExpansion = this.motion;
      this.scheduleDraw();
    }).catch(() => undefined);
  }

  cancel(preserveExpansion = false): void {
    this.generation++;
    if (this.frame) cancelAnimationFrame(this.frame);
    if (this.fadeTimer) clearTimeout(this.fadeTimer);
    this.frame = undefined;
    this.fadeTimer = undefined;
    this.motion = undefined;
    if (!preserveExpansion) {
      this.activeExpansionToken = undefined;
      this.pendingExpansion = undefined;
    }
    this.clearCanvas();
    const map = this.options.getMap();
    if (map?.getLayer("clusters")) {
      map.setPaintProperty("clusters", "icon-opacity", 1);
      map.setPaintProperty("clusters", "text-opacity", 1);
    }
  }

  private showAtomicTransition(): void {
    const map = this.options.getMap();
    if (!map || this.options.reducedMotion() || !map.getLayer("clusters")) return;
    map.setPaintProperty("clusters", "icon-opacity-transition", { duration: 150, delay: 0 });
    map.setPaintProperty("clusters", "text-opacity-transition", { duration: 150, delay: 0 });
    map.setPaintProperty("clusters", "icon-opacity", 0.001);
    map.setPaintProperty("clusters", "text-opacity", 0.001);
    this.fadeTimer = setTimeout(() => {
      if (map.getLayer("clusters")) {
        map.setPaintProperty("clusters", "icon-opacity", 1);
        map.setPaintProperty("clusters", "text-opacity", 1);
      }
    }, 16);
  }

  private scheduleDraw(): void {
    if (!this.frame) this.frame = requestAnimationFrame(() => this.draw());
  }

  private clearCanvas(): void {
    const canvas = this.canvas;
    canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
  }

  private draw(): void {
    this.frame = undefined;
    const canvas = this.canvas;
    const motion = this.motion;
    if (!canvas || !motion) return;
    const rect = canvas.getBoundingClientRect();
    const context = resizeMotionCanvas(canvas, rect.width, rect.height, window.devicePixelRatio || 1);
    if (!context) return;
    context.clearRect(0, 0, rect.width, rect.height);
    const progress = Math.min(1, (performance.now() - motion.startedAt) / motion.duration);
    const ease = 1 - Math.pow(1 - progress, 3);
    drawMotionDot(context, motion.origin, 1 - ease, 1 + ease * 0.14);
    for (const child of motion.children) {
      drawMotionDot(context, {
        ...child,
        x: motion.origin.x + (child.x - motion.origin.x) * ease,
        y: motion.origin.y + (child.y - motion.origin.y) * ease,
      }, ease, 0.68 + ease * 0.32);
    }
    if (progress < 1) {
      this.scheduleDraw();
      return;
    }
    this.motion = undefined;
    this.clearCanvas();
  }
}
