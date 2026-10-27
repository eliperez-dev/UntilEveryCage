/** A bounded visual bridge between native Supercluster levels. Never changes source data. */
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';
import { CATEGORY_PRIMARY_BY_SOURCE_KEY, CATEGORY_PIN_IMAGES } from '../../features/locations/categoryPresentation';
import { resizeMotionCanvas } from './mapSurfaceMotion';

export const DEFAULT_CLUSTER_MOTION_MS = 210;
export const DEFAULT_CLUSTER_MOTION_LIMIT = 200;
const LAYERS = ['clusters', 'v1-source-pins', 'approx-reference-pins', 'approx-reference-points'] as const;
const MASK_LAYERS = [...LAYERS, 'v1-source-shadows', 'approx-reference-shadows', 'approx-reference-cue', 'aggregate-count'];
type Properties = Record<string, unknown>;
type Node = { key: string; coordinates: [number, number]; properties: Properties; layer: string };
type Pair = { parent: Node; child: Node };
type Motion = { direction: 'split' | 'merge'; pairs: Pair[]; startedAt: number };
type Options = { getMap: () => MapLibreMap | undefined; reducedMotion: () => boolean; enabled: () => boolean; duration: () => number; limit: () => number };

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
  private motion: Motion | undefined;
  private pending = false;
  private armed = false;
  private played = false;
  private zoom = 0;
  private lastCameraZoom = 0;
  private direction: number | undefined;
  private images = new Map<string, { canvas: HTMLCanvasElement; pixelRatio: number }>();
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
    if (!map || !this.allowed()) return;
    this.zoom = map.getZoom();
    this.lastCameraZoom = this.zoom;
    this.before = this.capture();
    this.armed = Boolean(this.before);
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
    if (this.pending || this.motion || this.handoff || this.played || Math.abs(map.getZoom() - this.zoom) < 0.01) return;
    const after = this.capture(), before = this.before;
    if (!after || !before) { this.cancel(); return; }
    if (after.size === before.size && [...after.keys()].every(key => before.has(key))) {
      if (!map.isZooming() && map.isSourceLoaded('locations')) this.armed = false;
      return;
    }
    const direction = map.getZoom() > this.zoom ? 'split' : 'merge';
    this.pending = true;
    const generation = this.generation;
    const started = performance.now();
    void this.findPairs(direction === 'split' ? before : after, direction === 'split' ? after : before).then(pairs => {
      if (generation !== this.generation) return;
      this.pending = false;
      this.before = after; this.zoom = map.getZoom();
      // A slow worker must never postpone input or make settled pins jump back.
      if (!pairs.length || performance.now() - started > 100 || !this.allowed()) return;
      this.played = true;
      this.motion = { direction, pairs, startedAt: performance.now() };
      const incoming = direction === 'split' ? pairs.map(pair => pair.child.key) : pairs.map(pair => pair.parent.key);
      this.mask(incoming);
      this.canvas?.setAttribute('data-direction', direction);
      this.draw();
    }).catch(() => { if (generation === this.generation) this.cancel(); });
  }

  /** Panning/rotation, new data, style switches and deactivation invalidate all work. */
  cancel(clearImages = false): void {
    this.generation++; this.armed = false; this.pending = false; this.before = undefined;
    this.played = false;
    this.direction = undefined;
    this.children.clear(); this.motion = undefined;
    if (this.frame !== undefined) cancelAnimationFrame(this.frame);
    this.frame = undefined;
    if (clearImages) this.handoff?.finish();
    this.unmask(false); this.clear();
    if (clearImages) this.images.clear();
  }

  dispose(): void { this.cancel(true); this.handoff?.finish(); this.canvas?.remove(); this.canvas = undefined; }

  private allowed(): boolean { return this.options.enabled() && !this.options.reducedMotion() && this.options.duration() > 0; }

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
      if (nodes.size > Math.max(50, Math.min(300, this.options.limit()))) return;
    }
    return nodes;
  }

  private getChildren(node: Node): Promise<readonly Node[]> {
    const id = Number(node.properties.cluster_id);
    if (!Number.isSafeInteger(id)) return Promise.resolve([]);
    const cached = this.children.get(id);
    if (cached) return cached;
    const source = this.options.getMap()?.getSource('locations') as GeoJSONSource | undefined;
    const children = source?.getClusterChildren(id).then(features => features.flatMap(feature => {
      const key = clusterMotionKey(feature.properties ?? {});
      return key && feature.geometry.type === 'Point'
        ? [{ key, coordinates: feature.geometry.coordinates as [number, number], properties: feature.properties ?? {}, layer: node.layer }]
        : [];
    })).catch(() => []) ?? Promise.resolve([]);
    this.children.set(id, children);
    return children;
  }

  private async findPairs(parents: Map<string, Node>, targets: Map<string, Node>): Promise<Pair[]> {
    const pairs: Pair[] = [];
    const participants = new Set<string>();
    const limit = Math.max(50, Math.min(300, this.options.limit()));
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

  private mask(keys: string[]): void {
    // Complete any earlier cancellation handoff before recording the genuine
    // transition defaults for a new animation.
    this.handoff?.finish();
    const map = this.options.getMap(); if (!map) return;
    const key = ['case', ['has', 'cluster_id'], ['concat', 'c:', ['to-string', ['get', 'cluster_id']]], ['concat', 'p:', ['to-string', ['coalesce', ['get', 'key'], ['get', 'id'], ['get', 'facility_id'], '']]]];
    for (const layer of MASK_LAYERS) {
      if (!map.getLayer(layer)) continue;
      for (const property of ['icon-opacity', 'text-opacity'] as const) {
        const original = map.getPaintProperty(layer, property);
        this.originalPaint.set(`${layer}/${property}-transition`, map.getPaintProperty(layer, `${property}-transition`));
        map.setPaintProperty(layer, `${property}-transition`, { duration: 0, delay: 0 });
        this.originalPaint.set(`${layer}/${property}`, original);
        map.setPaintProperty(layer, property, ['case', ['in', key, ['literal', keys]], 0, original ?? 1] as never);
      }
    }
  }

  private unmask(retainCanvas: boolean): void {
    const map = this.options.getMap();
    if (!map || !this.originalPaint.size) { if (retainCanvas) { this.motion = undefined; this.clear(); } return; }
    this.handoff?.finish();
    const paint = [...this.originalPaint]; this.originalPaint.clear();
    const handoffMotion = this.motion;
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
        this.motion = undefined;
        if (this.frame !== undefined) cancelAnimationFrame(this.frame);
        this.frame = undefined; this.clear();
      }
    };
    const listener = () => {
      if (!map.getSource('locations') || map.isSourceLoaded('locations')) finish();
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
    const project = (coordinates: [number, number]) => map.project([coordinates[0] + Math.round((map.getCenter().lng - coordinates[0]) / 360) * 360, coordinates[1]]);
    const start = project(from.coordinates), end = project(to.coordinates);
    const x = start.x + (end.x - start.x) * progress, y = start.y + (end.y - start.y) * progress;
    const cluster = node.key.startsWith('c:'), image = this.image(clusterMotionImage(node.properties));
    if (!image) return;
    const nativeScale = Number(map.getLayoutProperty(node.layer, 'icon-size'));
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
    if (!cluster && ['approximate', 'city', 'city_reference_approximate', 'provider_locality_approximate', 'locality_reference_coarse'].includes(String(node.properties.precision))) {
      const cue = this.image('approximation-mark');
      if (cue) context.drawImage(cue.canvas, x + 17 * scale - cue.canvas.width * scale / 2, y - 21 * scale - cue.canvas.height * scale / 2, cue.canvas.width * scale, cue.canvas.height * scale);
    }
    context.restore();
  }

  private clear(): void { this.canvas?.getContext('2d')?.clearRect(0, 0, this.canvas.width, this.canvas.height); this.canvas?.removeAttribute('data-direction'); }

  private draw(): void {
    this.frame = undefined;
    const motion = this.motion, canvas = this.canvas;
    if (!motion || !canvas || !this.allowed()) { this.cancel(); return; }
    const rect = canvas.getBoundingClientRect(), context = resizeMotionCanvas(canvas, rect.width, rect.height, Math.min(2, window.devicePixelRatio || 1));
    if (!context) { this.cancel(); return; }
    context.clearRect(0, 0, rect.width, rect.height);
    const progress = Math.min(1, (performance.now() - motion.startedAt) / this.options.duration());
    const ease = 1 - Math.pow(1 - progress, 3), parents = new Set<string>();
    for (const { parent, child } of motion.pairs) {
      if (!parents.has(parent.key)) { this.drawNode(context, parent, parent, parent, 1, motion.direction === 'split' ? 1 - ease : ease); parents.add(parent.key); }
      // Native children have already reached their geographic positions when
      // this render detects them. Never pull them back to a parent's position.
      // The camera supplies the separation; the cue only crossfades the marks.
      this.drawNode(context, child, child, child, 1, motion.direction === 'split' ? ease : 1 - ease);
    }
    if (progress < 1) this.frame = requestAnimationFrame(() => this.draw());
    else {
      if (!this.handoff) this.unmask(true);
      // Keep the final marks projected into the moving camera until the native
      // repaint is ready. A static canvas here makes the handoff jump sideways.
      if (this.motion) this.frame = requestAnimationFrame(() => this.draw());
    }
  }
}
