/** A bounded visual bridge between native Supercluster levels. Never changes source data. */
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';
import { CATEGORY_PRIMARY_BY_SOURCE_KEY, CATEGORY_PIN_IMAGES } from '../../features/locations/categoryPresentation';
import { resizeMotionCanvas } from './mapSurfaceMotion';

export const DEFAULT_CLUSTER_MOTION_MS = 210;
export const DEFAULT_CLUSTER_MOTION_LIMIT = 1200;
export const MAX_CLUSTER_MOTION_LIMIT = 2000;
export const DEFAULT_CLUSTER_IDLE_MS = 0;
const NATIVE_PAINT_DEADLINE_MS = 500;
export type ClusterMotionState = 'idle' | 'holding' | 'settling' | 'pairing' | 'playing' | 'complete' | 'unchanged' | 'density-limit' | 'missing-artwork' | 'source-timeout' | 'pairing-timeout' | 'no-lineage' | 'interrupted' | 'data-change' | 'disabled';
const LAYERS = ['clusters', 'v1-source-pins', 'approx-reference-pins', 'approx-reference-points'] as const;
const MASK_LAYERS = [...LAYERS, 'v1-source-shadows', 'approx-reference-shadows', 'aggregate-count'];
type Properties = Record<string, unknown>;
type Node = { key: string; coordinates: [number, number]; properties: Properties; layer: string };
type Pair = { parent: Node; child: Node };
type Motion = { direction: 'split' | 'merge'; pairs: Pair[]; startedAt: number };
type Options = { getMap: () => MapLibreMap | undefined; reducedMotion: () => boolean; enabled: () => boolean; duration: () => number; limit: () => number; idleDelay?: () => number; onState?: (state: ClusterMotionState) => void };

/** The same stable identity exists in native children and rendered features. */
export function clusterMotionKey(properties: Properties): string | null {
  if (typeof properties.cluster_id === 'number') return `c:${properties.cluster_id}`;
  const key = properties.key ?? properties.id ?? properties.facility_id;
  return typeof key === 'string' || typeof key === 'number' ? `p:${key}` : null;
}

export function clusterMotionImage(properties: Properties): string {
  if (typeof properties.cluster_id === 'number') {
    const count = Number(properties.representedCount ?? properties.point_count);
    return `cluster-${count >= 1001 ? 'very-high' : count >= 100 ? 'high' : count >= 10 ? 'mid' : 'low'}`;
  }
  let keys = properties.category_keys;
  if (typeof keys === 'string') { try { keys = JSON.parse(keys); } catch { keys = []; } }
  const order = ['slaughter', 'research_and_animal_use', 'processing_and_preparation', 'animal_keeping_and_production', 'other_regulated_premises'] as const;
  const category = order.find(key => Array.isArray(keys) && keys.includes(key)) ?? CATEGORY_PRIMARY_BY_SOURCE_KEY[String(properties.category_key)];
  return CATEGORY_PIN_IMAGES[category ?? 'unclassified'] ?? CATEGORY_PIN_IMAGES.unclassified;
}

export class NativeClusterMotionController {
  private canvas: HTMLCanvasElement | undefined;
  private frame: number | undefined;
  private generation = 0;
  private before: Map<string, Node> | undefined;
  private children = new Map<number, Promise<readonly Node[]>>();
  private childCounts = new Map<number, number>();
  private hierarchySource: GeoJSONSource | undefined;
  private hierarchyGeneration = 0;
  private warming = false;
  private motion: Motion | undefined;
  private pending = false;
  private armed = false;
  private settleTimeout: ReturnType<typeof setTimeout> | undefined;
  private idleTimer: ReturnType<typeof setTimeout> | undefined;
  private settledAt: number | undefined;
  private placementStartedAt: number | undefined;
  private placementSignature: string | undefined;
  private after: Map<string, Node> | undefined;
  private zoom = 0;
  private lastCameraZoom = 0;
  private direction: number | undefined;
  private images = new Map<string, { canvas: HTMLCanvasElement; pixelRatio: number }>();
  private projected = new Map<string, { x: number; y: number }>();
  private frameCenter = 0;
  private frameScales = new Map<string, number>();
  private originalPaint = new Map<string, unknown>();
  private handoff: { map: MapLibreMap; listener: () => void; finish: () => void } | undefined;

  constructor(private readonly options: Options) {}

  attach(parent: HTMLElement): void {
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'native-cluster-motion';
    this.canvas.setAttribute('aria-hidden', 'true');
    Object.assign(this.canvas.style, { position: 'absolute', inset: '0', width: '100%', height: '100%', pointerEvents: 'none', zIndex: '3' });
    parent.append(this.canvas);
  }

  onZoomStart(): void {
    this.cancel();
    const map = this.options.getMap();
    if (!map || !this.allowed()) { this.report('disabled'); return; }
    this.zoom = map.getZoom();
    this.lastCameraZoom = this.zoom;
    this.before = this.capture();
    if (!this.before?.size) { this.before = undefined; this.report('density-limit'); return; }
    if ([...this.before.values()].some(node => !this.image(clusterMotionImage(node.properties)))) { this.before = undefined; this.report('missing-artwork'); return; }
    this.armed = true;
    this.report('holding');
    // Own the bounded snapshot before the renderer changes cluster levels.
    // Waiting to hide children until a later render flashes their destinations
    // first, then visibly pulls them backwards to their parent.
    this.mask();
    this.canvas?.setAttribute('data-phase', 'holding');
    this.draw();
    // Prime actual immediate children while the camera begins its existing ease.
    // These are native read-only queries, never a new index or a point projection.
    if (this.before) for (const node of [...this.before.values()].filter(node => node.key.startsWith('c:')).slice(0, 40)) void this.getChildren(node);
  }

  onRender(): void {
    if (!this.armed || !this.allowed()) return;
    const map = this.options.getMap();
    if (!map) return;
    const delta = map.getZoom() - this.lastCameraZoom;
    if (Math.abs(delta) > 0.001) {
      if (this.direction !== undefined && Math.sign(delta) !== this.direction) { this.cancel(); return; }
      this.direction = Math.sign(delta);
    }
    this.lastCameraZoom = map.getZoom();
    if (this.pending || this.motion || this.handoff) return;
    // Like Leaflet.markercluster, resolve one final hierarchy after the camera
    // zoom. Intermediate native levels stay behind the following snapshot.
    if (map.isZooming()) return;
    this.settledAt ??= performance.now();
    const remaining = Math.max(0, Math.min(500, this.options.idleDelay?.() ?? DEFAULT_CLUSTER_IDLE_MS)) - (performance.now() - this.settledAt);
    if (remaining > 0) {
      this.report('settling');
      if (this.idleTimer === undefined) this.idleTimer = setTimeout(() => { this.idleTimer = undefined; this.onRender(); }, remaining);
      return;
    }
    if (!map.isSourceLoaded('locations')) {
      if (this.settleTimeout === undefined) {
        const generation = this.generation;
        this.settleTimeout = setTimeout(() => {
          if (generation !== this.generation) return;
          // Source completion can precede the next native render (notably in
          // Firefox). Use its ready hierarchy rather than aborting a valid cue.
          if (this.options.getMap()?.isSourceLoaded('locations')) this.onRender();
          else this.cancel(false, 'source-timeout');
        }, NATIVE_PAINT_DEADLINE_MS);
      }
      return;
    }
    clearTimeout(this.settleTimeout); this.settleTimeout = undefined;
    if (Math.abs(map.getZoom() - this.zoom) < 0.01) { this.revealSnapshot(); return; }
    const after = this.capture(), before = this.before;
    if (!after || !before) { this.cancel(false, 'density-limit'); return; }
    // Worker/source readiness precedes native symbol placement. The first
    // post-zoom frame can still be empty or show the previous tile hierarchy.
    // Confirm a nonempty stable paint instead of treating that as no lineage.
    this.placementStartedAt ??= performance.now();
    const signature = [...after.keys()].sort().join('|');
    if (!after.size || signature !== this.placementSignature) {
      if (performance.now() - this.placementStartedAt > NATIVE_PAINT_DEADLINE_MS) { this.cancel(false, 'source-timeout'); return; }
      this.placementSignature = signature;
      map.triggerRepaint();
      return;
    }
    if (after.size === before.size && [...after.keys()].every(key => before.has(key))) {
      this.revealSnapshot();
      return;
    }
    const direction = map.getZoom() > this.zoom ? 'split' : 'merge';
    this.pending = true;
    this.report('pairing');
    const generation = this.generation;
    const started = performance.now();
    const timeout = setTimeout(() => { if (generation === this.generation && this.pending) this.cancel(false, 'pairing-timeout'); }, 100);
    void this.findPairs(direction === 'split' ? before : after, direction === 'split' ? after : before).then(pairs => {
      clearTimeout(timeout);
      if (generation !== this.generation) return;
      this.pending = false;
      // A slow worker must never postpone input or make settled pins jump back.
      const visibleMarks = new Set([...after.keys(), ...pairs.flatMap(pair => [pair.parent.key, pair.child.key])]).size;
      if (!pairs.length || visibleMarks > this.markLimit() || performance.now() - started > 100 || !this.allowed()) { this.cancel(false, !pairs.length ? 'no-lineage' : visibleMarks > this.markLimit() ? 'density-limit' : 'pairing-timeout'); return; }
      this.armed = false;
      this.after = after;
      this.motion = { direction, pairs, startedAt: performance.now() };
      this.report('playing');
      this.canvas?.setAttribute('data-phase', 'moving');
      this.canvas?.setAttribute('data-direction', direction);
      this.draw();
    }).catch(() => { clearTimeout(timeout); if (generation === this.generation) this.cancel(); });
  }

  /** Panning/rotation, new data, style switches and deactivation invalidate all work. */
  cancel(clearImages = false, reason: ClusterMotionState = 'interrupted'): void {
    this.generation++; this.armed = false; this.pending = false; this.before = undefined;
    clearTimeout(this.settleTimeout); this.settleTimeout = undefined; this.after = undefined;
    clearTimeout(this.idleTimer); this.idleTimer = undefined; this.settledAt = undefined;
    this.placementStartedAt = undefined; this.placementSignature = undefined;
    this.direction = undefined;
    this.motion = undefined;
    if (this.frame !== undefined) cancelAnimationFrame(this.frame);
    this.frame = undefined;
    if (clearImages) this.handoff?.finish();
    // Data/restriction changes must discard the old snapshot immediately.
    this.unmask(false); this.clear();
    if (clearImages) { this.images.clear(); this.clearHierarchy(); }
    this.report(reason);
  }

  /** Index/filter/restriction changes invalidate cached lineage, camera moves do not. */
  invalidate(): void { this.cancel(false, 'data-change'); this.clearHierarchy(); }

  onSourceReady(): void {
    if (!this.armed || !this.options.getMap()?.isSourceLoaded('locations')) return;
    clearTimeout(this.settleTimeout); this.settleTimeout = undefined;
    this.options.getMap()?.triggerRepaint();
  }

  /** Warm a bounded native hierarchy while idle, not a parallel cluster index. */
  async warm(): Promise<void> {
    const map = this.options.getMap();
    if (!map || map.isMoving() || !map.isSourceLoaded('locations') || !this.allowed() || this.warming) return;
    const nodes = this.capture(); if (!nodes) return;
    const source = map.getSource('locations') as GeoJSONSource | undefined;
    if (source !== this.hierarchySource) { this.clearHierarchy(); this.hierarchySource = source; }
    this.warming = true;
    const generation = this.hierarchyGeneration;
    const queue = [...nodes.values()].filter(node => node.key.startsWith('c:')).map(node => ({ node, depth: 0 }));
    let queries = 0;
    try {
      while (queue.length && queries < 80 && generation === this.hierarchyGeneration) {
        const batch = queue.splice(0, Math.min(8, 80 - queries)); queries += batch.length;
        const rows = await Promise.all(batch.map(({ node }) => this.getChildren(node)));
        if (generation !== this.hierarchyGeneration) return;
        rows.forEach((children, index) => { if (batch[index]!.depth < 3) for (const child of children) if (child.key.startsWith('c:')) queue.push({ node: child, depth: batch[index]!.depth + 1 }); });
      }
    } finally { if (generation === this.hierarchyGeneration) this.warming = false; }
  }

  private report(state: ClusterMotionState): void { this.canvas?.setAttribute('data-state', state); this.options.onState?.(state); }
  private clearHierarchy(): void { this.children.clear(); this.childCounts.clear(); this.hierarchySource = undefined; this.hierarchyGeneration++; this.warming = false; }
  private markLimit(): number { return Math.max(50, Math.min(MAX_CLUSTER_MOTION_LIMIT, this.options.limit())); }

  dispose(): void { this.cancel(true); this.handoff?.finish(); this.canvas?.remove(); this.canvas = undefined; }

  private allowed(): boolean { return this.options.enabled() && !this.options.reducedMotion() && this.options.duration() > 0; }

  /** No hierarchy changed: hand the matching snapshot back without a blank frame. */
  private revealSnapshot(): void {
    this.report('unchanged');
    this.armed = false; this.before = undefined;
    if (this.frame !== undefined) cancelAnimationFrame(this.frame);
    this.frame = undefined;
    this.unmask(true);
  }

  private capture(): Map<string, Node> | undefined {
    const map = this.options.getMap();
    if (!map) return;
    const layers = LAYERS.filter(layer => map.getLayer(layer) && map.getLayoutProperty(layer, 'visibility') !== 'none');
    if (!layers.length) return;
    const nodes = new Map<string, Node>();
    for (const feature of map.queryRenderedFeatures({ layers })) {
      const key = clusterMotionKey(feature.properties);
      if (!key || feature.geometry.type !== 'Point' || nodes.has(key)) continue;
      nodes.set(key, { key, coordinates: feature.geometry.coordinates as [number, number], properties: feature.properties, layer: feature.layer.id });
      if (nodes.size > this.markLimit()) return;
    }
    return nodes;
  }

  private getChildren(node: Node): Promise<readonly Node[]> {
    const id = Number(node.properties.cluster_id);
    if (!Number.isSafeInteger(id)) return Promise.resolve([]);
    const source = this.options.getMap()?.getSource('locations') as GeoJSONSource | undefined;
    if (source !== this.hierarchySource) { this.clearHierarchy(); this.hierarchySource = source; }
    const cached = this.children.get(id);
    if (cached) return cached;
    const generation = this.hierarchyGeneration;
    const children: Promise<readonly Node[]> = source?.getClusterChildren(id).then(features => features.flatMap(feature => {
      const key = clusterMotionKey(feature.properties ?? {});
      return key && feature.geometry.type === 'Point'
        ? [{ key, coordinates: feature.geometry.coordinates as [number, number], properties: feature.properties ?? {}, layer: node.layer }]
        : [];
    })).then(nodes => {
      if (generation !== this.hierarchyGeneration) return [];
      if (this.children.get(id) !== children) return nodes;
      this.childCounts.set(id, nodes.length);
      let count = [...this.childCounts.values()].reduce((sum, value) => sum + value, 0);
      while (this.children.size > 512 || count > 4096) {
        const oldest = this.children.keys().next().value; if (oldest === undefined) break;
        count -= this.childCounts.get(oldest) ?? 0;
        this.children.delete(oldest); this.childCounts.delete(oldest);
      }
      if (!nodes.length) { this.children.delete(id); this.childCounts.delete(id); }
      return nodes;
    }).catch(() => { if (generation === this.hierarchyGeneration) { this.children.delete(id); this.childCounts.delete(id); } return []; }) ?? Promise.resolve([]);
    this.children.set(id, children);
    while (this.children.size > 512) { const oldest = this.children.keys().next().value!; this.children.delete(oldest); this.childCounts.delete(oldest); }
    return children;
  }

  private async findPairs(parents: Map<string, Node>, targets: Map<string, Node>): Promise<Pair[]> {
    const pairs: Pair[] = [];
    const participants = new Set<string>();
    const limit = this.markLimit();
    const generation = this.generation;
    let queries = 0;
    const queue = [...parents.values()].filter(parent => parent.key.startsWith('c:') && !targets.has(parent.key))
      .map(parent => ({ parent, node: parent, depth: 0 }));
    while (queue.length && queries < 80) {
      // Batch independent native reads. A long serial child walk otherwise
      // misses the brief transition window while normal tiles are loading.
      const batch = queue.splice(0, Math.min(16, 80 - queries)); queries += batch.length;
      const results = await Promise.all(batch.map(item => this.getChildren(item.node)));
      if (generation !== this.generation) return [];
      for (const [index, children] of results.entries()) {
        const item = batch[index]!;
        for (const child of children) {
          const target = targets.get(child.key);
          if (target) {
            const added = Number(!participants.has(item.parent.key)) + Number(!participants.has(target.key));
            if (participants.size + added > limit) return pairs;
            participants.add(item.parent.key); participants.add(target.key);
            pairs.push({ parent: item.parent, child: target });
          } else if (child.key.startsWith('c:') && item.depth < 4) queue.push({ parent: item.parent, node: child, depth: item.depth + 1 });
          if (participants.size >= limit) return pairs;
        }
      }
    }
    return pairs;
  }

  private mask(): void {
    // Complete any earlier cancellation handoff before recording the genuine
    // transition defaults for a new animation.
    this.handoff?.finish();
    const map = this.options.getMap(); if (!map) return;
    for (const layer of MASK_LAYERS) {
      if (!map.getLayer(layer)) continue;
      for (const property of ['icon-opacity', 'text-opacity'] as const) {
        const original = map.getPaintProperty(layer, property);
        this.originalPaint.set(`${layer}/${property}-transition`, map.getPaintProperty(layer, `${property}-transition`));
        map.setPaintProperty(layer, `${property}-transition`, { duration: 0, delay: 0 });
        this.originalPaint.set(`${layer}/${property}`, original);
        // Constant zero makes MapLibre skip drawSymbol entirely, so freshly
        // loaded tiles never populate the symbol-query metadata we need.
        // Feature-dependent zero keeps native placement/querying active while
        // the canvas owns the visible marks.
        map.setPaintProperty(layer, property, ['case', ['has', 'cluster_id'], 0, 0] as never);
      }
    }
  }

  private unmask(retainCanvas: boolean): void {
    const map = this.options.getMap();
    if (!map || !this.originalPaint.size) { if (retainCanvas) { this.motion = undefined; this.clear(); } return; }
    this.handoff?.finish();
    const paint = [...this.originalPaint]; this.originalPaint.clear();
    const handoffMotion = this.motion;
    const handoffStarted = performance.now();
    // MapLibre coalesces paint changes in a frame. Restoring its default
    // transition in this same tick would add another 300ms opacity fade.
    for (const [key, value] of paint.filter(([key]) => !key.endsWith('-transition'))) {
      const [layer, property] = key.split('/');
      if (layer && property && map.getLayer(layer)) map.setPaintProperty(layer, property as Parameters<MapLibreMap['setPaintProperty']>[1], value as never);
    }
    const finish = () => {
      if (this.handoff?.listener !== listener) return;
      map.off('render', listener); this.handoff = undefined;
      for (const [key, value] of paint.filter(([key]) => key.endsWith('-transition'))) {
        const [layer, property] = key.split('/');
        if (layer && property && map.getLayer(layer)) map.setPaintProperty(layer, property as Parameters<MapLibreMap['setPaintProperty']>[1], value as never);
      }
      if (retainCanvas && this.motion === handoffMotion) {
        if (handoffMotion) this.report('complete');
        this.motion = undefined;
        if (this.frame !== undefined) cancelAnimationFrame(this.frame);
        this.frame = undefined; this.clear();
      }
    };
    const listener = () => {
      if (!handoffMotion || !map.getSource('locations') || map.isSourceLoaded('locations') || performance.now() - handoffStarted > NATIVE_PAINT_DEADLINE_MS) finish();
    };
    this.handoff = { map, listener, finish };
    map.on('render', listener); map.triggerRepaint();
  }

  private image(id: string): { canvas: HTMLCanvasElement; pixelRatio: number } | undefined {
    const cached = this.images.get(id); if (cached) return cached;
    const image = this.options.getMap()?.getImage(id);
    if (!image?.data) return;
    const canvas = document.createElement('canvas'); canvas.width = image.data.width; canvas.height = image.data.height;
    canvas.getContext('2d')?.putImageData(new ImageData(new Uint8ClampedArray(image.data.data), canvas.width, canvas.height), 0, 0);
    const result = { canvas, pixelRatio: image.pixelRatio || 1 }; this.images.set(id, result); return result;
  }

  private drawNode(context: CanvasRenderingContext2D, node: Node, from: Node, to: Node, progress: number, opacity: number): void {
    const map = this.options.getMap(); if (!map || opacity <= 0) return;
    const project = (value: Node) => {
      let pixel = this.projected.get(value.key);
      if (!pixel) { const coordinates = value.coordinates; pixel = map.project([coordinates[0] + Math.round((this.frameCenter - coordinates[0]) / 360) * 360, coordinates[1]]); this.projected.set(value.key, pixel); }
      return pixel;
    };
    const start = project(from), end = from.key === to.key ? start : project(to);
    const x = start.x + (end.x - start.x) * progress, y = start.y + (end.y - start.y) * progress;
    const cluster = node.key.startsWith('c:'), image = this.image(clusterMotionImage(node.properties));
    if (!image) return;
    let nativeScale = this.frameScales.get(node.layer);
    if (nativeScale === undefined) { nativeScale = Number(map.getLayoutProperty(node.layer, 'icon-size')); this.frameScales.set(node.layer, nativeScale); }
    const scale = Number.isFinite(nativeScale) ? nativeScale : cluster ? 1 : 0.5;
    const width = image.canvas.width / image.pixelRatio * scale, height = image.canvas.height / image.pixelRatio * scale;
    context.save(); context.globalAlpha = opacity;
    if (!cluster && node.layer !== 'approx-reference-points') {
      const shadow = this.image('v1-pin-shadow');
      if (shadow) {
        const shadowWidth = shadow.canvas.width / shadow.pixelRatio * scale * 2, shadowHeight = shadow.canvas.height / shadow.pixelRatio * scale * 2;
        context.drawImage(shadow.canvas, x - shadowWidth / 2 + 17 * scale, y - shadowHeight, shadowWidth, shadowHeight);
      }
    }
    context.drawImage(image.canvas, x - width / 2, y - (cluster ? height / 2 : height), width, height);
    const count = Number(node.properties.representedCount ?? node.properties.point_count ?? node.properties.weight ?? 1);
    if (cluster || count > 1) {
      context.fillStyle = '#172019'; context.font = `700 ${cluster ? 12 : 11}px "Open Sans", sans-serif`; context.textAlign = 'center'; context.textBaseline = 'middle';
      context.fillText(String(count), x, y);
    }
    context.restore();
  }

  private clear(): void { this.canvas?.getContext('2d')?.clearRect(0, 0, this.canvas.width, this.canvas.height); this.canvas?.removeAttribute('data-direction'); this.canvas?.removeAttribute('data-phase'); }

  private draw(): void {
    if (this.frame !== undefined) cancelAnimationFrame(this.frame);
    this.frame = undefined;
    const motion = this.motion, canvas = this.canvas;
    if (!canvas || !this.allowed()) { this.cancel(); return; }
    this.projected.clear(); this.frameScales.clear(); this.frameCenter = this.options.getMap()?.getCenter().lng ?? 0;
    const rect = canvas.getBoundingClientRect(), context = resizeMotionCanvas(canvas, rect.width, rect.height, Math.min(2, window.devicePixelRatio || 1));
    if (!context) { this.cancel(); return; }
    context.clearRect(0, 0, rect.width, rect.height);
    if (!motion) {
      if (!this.before || (!this.armed && !this.pending)) return;
      for (const node of this.before.values()) this.drawNode(context, node, node, node, 1, 1);
      this.frame = requestAnimationFrame(() => this.draw());
      return;
    }
    const progress = Math.min(1, (performance.now() - motion.startedAt) / this.options.duration());
    const ease = 1 - Math.pow(1 - progress, 3), parents = new Set<string>();
    const participants = new Set(motion.pairs.flatMap(({ parent, child }) => [parent.key, child.key]));
    for (const node of this.after?.values() ?? []) if (!participants.has(node.key)) this.drawNode(context, node, node, node, 1, 1);
    for (const { parent, child } of motion.pairs) {
      if (!parents.has(parent.key)) { this.drawNode(context, parent, parent, parent, 1, motion.direction === 'split' ? 1 - ease : ease); parents.add(parent.key); }
      this.drawNode(context, child, motion.direction === 'split' ? parent : child, motion.direction === 'split' ? child : parent, ease, motion.direction === 'split' ? ease : 1 - ease);
    }
    if (progress < 1) this.frame = requestAnimationFrame(() => this.draw());
    else {
      if (!this.handoff) this.unmask(true);
      // A settled camera can otherwise go idle after the first restore frame
      // while symbols are still pending, leaving the canvas stranded forever.
      if (this.handoff) this.options.getMap()?.triggerRepaint();
      // Keep the final marks projected into the moving camera until the native
      // repaint is ready. A static canvas here makes the handoff jump sideways.
      if (this.motion) this.frame = requestAnimationFrame(() => this.draw());
    }
  }
}
