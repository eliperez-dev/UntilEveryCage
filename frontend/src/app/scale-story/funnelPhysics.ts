import { funnelColumn, seed, type FunnelLayout, type ParticleVisitor } from './engine';

const STEP = 1 / 60;
const MAX_GAP = .125;
const MAX_PARTICLES = 160_000;
const DRAG = 1.4;
const MARGIN = 3;

export type FunnelPhysicsStats = Readonly<{
  rate: number; seconds: number; emitted: number; alive: number; retired: number;
  materialized: number; capacity: number; rebuilds: number; gridCells: number;
  lastSteps: number;
}>;

/** Optional visual outflow only; the source lattice and crossing identities stay
 * in engine.ts. A uniform-cell pressure/alignment field approximates local
 * crowding, not pairwise hard-body collisions. No individuals are sampled.
 *
 * State is dense typed arrays. Positive downward speed guarantees a finite
 * visible lifetime; retirement occurs only outside the frame. First use,
 * resize, backwards seeks and long gaps reconstruct the recent free-flight
 * population, rather than replaying historical interaction steps. Crossings
 * outside that bounded window are still included in emitted/retired totals.
 */
export function createFunnelOutflowPhysics(rate: number) {
  if (!Number.isFinite(rate) || rate <= 0 || rate > 100_000) throw new RangeError('Unsupported funnel particle rate.');
  let ids = new Float64Array(0), xs = new Float32Array(0), ys = new Float32Array(0);
  let vxs = new Float32Array(0), vys = new Float32Array(0);
  let counts = new Uint32Array(0), sumX = new Float32Array(0), sumY = new Float32Array(0);
  let alive = 0, capacity = 0, time = 0, emitted = 0, materialized = 0, rebuilds = 0;
  let width = 0, height = 0, throat = 0, columns = 0, columnStep = 0, throatWidth = 0, exitSpeed = 0;
  let gridColumns = 0, gridRows = 0, minDown = 0, gravity = 0, maxAge = 0, configured = false, initialized = false;
  const diagnostic = { rate, seconds: 0, emitted: 0, alive: 0, retired: 0, materialized: 0, capacity: 0, rebuilds: 0, gridCells: 0, lastSteps: 0 };

  function checkTime(seconds: number) {
    if (!Number.isFinite(seconds) || seconds < 0 || !Number.isSafeInteger(Math.floor(seconds * rate))) throw new RangeError('Invalid funnel time.');
  }
  function changed(layout: FunnelLayout) {
    return !configured || width !== layout.width || height !== layout.height || throat !== layout.throat
      || columns !== layout.columns || columnStep !== layout.step || throatWidth !== layout.throatHalfWidth || exitSpeed !== layout.exitSpeed;
  }
  function configure(layout: FunnelLayout) {
    if (![layout.width, layout.height, layout.throat, layout.throatHalfWidth, layout.exitSpeed].every(Number.isFinite)
      || layout.width <= 0 || layout.height <= 0 || layout.throat < 0 || layout.throat > layout.height
      || layout.throatHalfWidth < 0 || layout.throatHalfWidth > layout.width / 2 || layout.exitSpeed <= 0
      || !Number.isSafeInteger(layout.columns) || layout.columns < 1 || !Number.isSafeInteger(layout.step) || layout.step < 1) throw new RangeError('Invalid funnel geometry.');
    width = layout.width; height = layout.height; throat = layout.throat; columns = layout.columns;
    columnStep = layout.step; throatWidth = layout.throatHalfWidth; exitSpeed = layout.exitSpeed;
    minDown = Math.max(48, height * .75, exitSpeed * .35);
    gravity = Math.max(height * 1.7, minDown * DRAG * 1.2);
    maxAge = (height + MARGIN - throat) / minDown + STEP * 2;
    const required = Math.ceil(rate * (maxAge + STEP)) + 8;
    if (required > MAX_PARTICLES) throw new RangeError('Funnel geometry exceeds the complete-particle capacity.');
    if (required > capacity) {
      capacity = required; ids = new Float64Array(capacity); xs = new Float32Array(capacity); ys = new Float32Array(capacity);
      vxs = new Float32Array(capacity); vys = new Float32Array(capacity);
    }
    gridColumns = Math.max(1, Math.min(96, Math.ceil(width / 12)));
    gridRows = Math.max(1, Math.min(96, Math.ceil((height - throat + MARGIN) / 12)));
    const cells = gridColumns * gridRows;
    counts = new Uint32Array(cells); sumX = new Float32Array(cells); sumY = new Float32Array(cells);
    configured = true;
  }
  function outside(x: number, y: number) { return x < -MARGIN || x > width + MARGIN || y < -MARGIN || y > height + MARGIN; }
  function append(id: number, seconds: number, layout: FunnelLayout) {
    const column = funnelColumn(id, layout), side = columns === 1 ? 0 : column / (columns - 1) * 2 - 1;
    const age = Math.max(0, seconds - id / rate), decay = Math.exp(-DRAG * age), distance = (1 - decay) / DRAG;
    const vx = (seed(id, 431) * 2 - 1) * width * 1.15 + side * width * .18;
    const vy = Math.max(minDown, exitSpeed * (.7 + seed(id, 433) * .65));
    const terminal = gravity / DRAG;
    const x = width / 2 + side * throatWidth + vx * distance;
    const y = throat + terminal * age + (vy - terminal) * distance;
    materialized++;
    if (outside(x, y)) return;
    if (alive >= capacity) throw new RangeError('Complete funnel particle capacity exceeded.');
    ids[alive] = id; xs[alive] = x; ys[alive] = y; vxs[alive] = vx * decay;
    vys[alive] = terminal + (vy - terminal) * decay; alive++;
  }
  function cell(x: number, y: number) {
    const column = Math.max(0, Math.min(gridColumns - 1, Math.floor(x / width * gridColumns)));
    const row = Math.max(0, Math.min(gridRows - 1, Math.floor((y - throat) / Math.max(1, height - throat + MARGIN) * gridRows)));
    return row * gridColumns + column;
  }
  function integrate(dt: number) {
    counts.fill(0); sumX.fill(0); sumY.fill(0);
    for (let i = 0; i < alive; i++) {
      const key = cell(xs[i]!, ys[i]!);
      counts[key] = counts[key]! + 1; sumX[key] = sumX[key]! + vxs[i]!; sumY[key] = sumY[key]! + vys[i]!;
    }
    const decay = Math.exp(-DRAG * dt);
    for (let i = 0; i < alive;) {
      const key = cell(xs[i]!, ys[i]!), column = key % gridColumns, row = Math.floor(key / gridColumns);
      const local = counts[key]!;
      const left = column > 0 ? counts[key - 1]! : 0, right = column + 1 < gridColumns ? counts[key + 1]! : 0;
      const above = row > 0 ? counts[key - gridColumns]! : 0, below = row + 1 < gridRows ? counts[key + gridColumns]! : 0;
      // Bounded mean-field gradients + local velocity alignment are O(1) per
      // individual, even where tens of thousands share the throat region.
      const ax = (left - right) / (local + left + right + 1) * width * 2.5
        + (sumX[key]! / Math.max(1, local) - vxs[i]!) * 1.3;
      const ay = (above - below) / (local + above + below + 1) * height * .65
        + (sumY[key]! / Math.max(1, local) - vys[i]!) * .7;
      vxs[i] = vxs[i]! * decay + ax / DRAG * (1 - decay);
      vys[i] = Math.max(minDown, vys[i]! * decay + (gravity + ay) / DRAG * (1 - decay));
      xs[i] = xs[i]! + vxs[i]! * dt; ys[i] = ys[i]! + vys[i]! * dt;
      if (outside(xs[i]!, ys[i]!)) {
        alive--; ids[i] = ids[alive]!; xs[i] = xs[alive]!; ys[i] = ys[alive]!; vxs[i] = vxs[alive]!; vys[i] = vys[alive]!;
      } else i++;
    }
  }
  function publish() {
    diagnostic.seconds = time; diagnostic.emitted = emitted; diagnostic.alive = alive;
    diagnostic.retired = emitted - alive; diagnostic.materialized = materialized;
    diagnostic.capacity = capacity; diagnostic.rebuilds = rebuilds; diagnostic.gridCells = counts.length;
  }
  function seek(seconds: number, layout: FunnelLayout) {
    alive = 0; rebuilds++; emitted = Math.floor(seconds * rate);
    // Older identities must be offscreen: normal integration never permits
    // vertical speed below minDown. Rebuild only the complete recent window.
    const first = Math.max(1, Math.floor((seconds - maxAge) * rate) + 1);
    for (let id = first; id <= emitted; id++) append(id, seconds, layout);
    time = seconds; initialized = true;
  }
  return {
    reset(seconds = 0) {
      checkTime(seconds); alive = 0; time = seconds; emitted = Math.floor(seconds * rate);
      materialized = 0; rebuilds = 0; initialized = false; diagnostic.lastSteps = 0; publish();
    },
    advance(seconds: number, layout: FunnelLayout) {
      checkTime(seconds); diagnostic.lastSteps = 0;
      const resize = changed(layout);
      if (resize) configure(layout);
      if (!initialized || resize || seconds < time || seconds - time > MAX_GAP) { seek(seconds, layout); publish(); return; }
      if (seconds === time) return;
      const start = time, steps = Math.max(1, Math.ceil((seconds - start) / STEP));
      diagnostic.lastSteps = steps;
      for (let step = 1; step <= steps; step++) {
        const end = step === steps ? seconds : start + (seconds - start) * step / steps;
        integrate(end - time);
        const crossed = Math.floor(end * rate);
        for (let id = emitted + 1; id <= crossed; id++) append(id, end, layout);
        emitted = crossed; time = end;
      }
      publish();
    },
    visit(visitor: ParticleVisitor) { for (let i = 0; i < alive; i++) visitor(ids[i]!, xs[i]!, ys[i]!, true); },
    /** A read-only live diagnostic view. Copy it when retaining a snapshot. */
    stats(): FunnelPhysicsStats { return diagnostic; },
  };
}

export type FunnelOutflowPhysics = ReturnType<typeof createFunnelOutflowPhysics>;
