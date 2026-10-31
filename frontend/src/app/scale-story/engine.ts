/** Dated annual means, deliberately separate from map release aggregates. */
export const STORY_RATES = { land: 2779, fish: 65671 } as const;
export type StoryPopulation = keyof typeof STORY_RATES;
export type StoryMode = 'funnel' | 'grid';
export const GRID_BATCH_SECONDS = 0.25;
export const FUNNEL_QUEUE_SECONDS = 1.2;
export const FUNNEL_RED_SECONDS = 1;
export const CHICKEN_LINE_RATE = 140 / 60;

/** Integrate active time, not frames. Analytic rendering never replays missed events. */
export class ActiveStoryClock {
  private activeMilliseconds = 0;
  private compensation = 0;
  private previous: number | null = null;
  private running = false;
  get elapsed() { return this.activeMilliseconds / 1000; }
  setRunning(running: boolean, now: number) {
    this.advance(now);
    this.running = running;
    this.previous = running ? now : null;
  }
  advance(now: number) {
    if (this.running && this.previous !== null && Number.isFinite(now)) {
      const delta = Math.max(0, now - this.previous) - this.compensation;
      const total = this.activeMilliseconds + delta;
      this.compensation = (total - this.activeMilliseconds) - delta;
      this.activeMilliseconds = total;
      this.previous = Math.max(this.previous, now);
    }
    return this.elapsed;
  }
  reset(now: number) { this.activeMilliseconds = 0; this.compensation = 0; this.previous = this.running ? now : null; }
  emitted(rate: number) { return Math.floor(this.activeMilliseconds * rate / 1000); }
}

export function seed(id: number, salt = 0): number {
  let value = Math.imul((id ^ salt) >>> 0, 0x45d9f3b);
  value = Math.imul(value ^ (value >>> 16), 0x45d9f3b);
  return ((value ^ (value >>> 16)) >>> 0) / 4294967296;
}

export function batchBounds(batch: number, rate: number) {
  return { first: Math.floor(batch * GRID_BATCH_SECONDS * rate) + 1,
    last: Math.floor((batch + 1) * GRID_BATCH_SECONDS * rate) };
}

export function snakePosition(index: number, columns: number) {
  const row = Math.floor(index / columns), offset = index % columns;
  return { column: row % 2 ? columns - 1 - offset : offset, row };
}

export type ParticleVisitor = (id: number, x: number, y: number, dead: boolean) => void;

/** Separate line-crossing comparison; fractional rates retain individual identities. */
export function lineParticles(seconds: number, rate: number, width: number, height: number, visit: ParticleVisitor) {
  const first = Math.max(1, Math.floor((seconds - 2) * rate));
  const last = Math.floor((seconds + 1.6) * rate);
  let count = 0;
  for (let id = first; id <= last; id++) {
    const age = seconds - id / rate, y = height * .48 + age * height * .23;
    if (y < -16 || y > height + 16) continue;
    visit(id, width * (.5 + (seed(id, 41) - .5) * .38), y, age >= 0); count++;
  }
  return count;
}

export interface FunnelLayout {
  width: number; height: number; columns: number; step: number; spacing: number;
  left: number; right: number; top: number; front: number; throat: number;
  rowSeconds: number; feedSpeed: number; pullSeconds: number; queueSeconds: number;
  exitSpeed: number; redSeconds: number; throatHalfWidth: number;
}

function gcd(a: number, b: number): number { while (b) { const next = a % b; a = b; b = next; } return a; }

/** Geometry and durations adapt to density, never to a reduced individual rate. */
export function funnelLayout(rate: number, width: number, height: number): FunnelLayout {
  const mobile = width < 500, gridWidth = width * (mobile ? .84 : .74);
  const top = height * .045, front = height * .43, throat = height * .70;
  const targetPitch = rate > 10000 ? (mobile ? 2.5 : 2.8) : (mobile ? 8.4 : 10.8);
  const columns = Math.max(1, Math.min(Math.floor(gridWidth / targetPitch) + 1,
    Math.floor(Math.sqrt(rate * .7 * gridWidth / (front - top)))));
  const spacing = columns > 1 ? gridWidth / (columns - 1) : (front - top) / (rate * .7);
  const rowSeconds = columns / rate, feedSpeed = spacing / rowSeconds;
  const pullSeconds = Math.min(.5, (throat - front) * .9 / feedSpeed);
  const queueSeconds = Math.min(FUNNEL_QUEUE_SECONDS, (front - top) / feedSpeed + pullSeconds);
  const exitSpeed = (throat - front) / pullSeconds;
  const redSeconds = Math.min(FUNNEL_RED_SECONDS, (height + 3 - throat) * 1.5 / exitSpeed);
  const throatHalfWidth = columns > 1 ? Math.min(gridWidth / 2, Math.max(14, Math.min(28, width * .028))) : 0;
  let step = Math.max(1, Math.floor(columns * .618));
  while (gcd(step, columns) !== 1) step++;
  return { width, height, columns, step, spacing, left: (width - gridWidth) / 2,
    right: (width + gridWidth) / 2, top, front, throat, rowSeconds, feedSpeed,
    pullSeconds, queueSeconds, exitSpeed, redSeconds, throatHalfWidth };
}

/** A bijection visits every lattice column once, without a left-to-right wipe. */
export function funnelColumn(id: number, layout: FunnelLayout) {
  const row = Math.floor((id - 1) / layout.columns), offset = (id - 1) % layout.columns;
  return (offset * layout.step + (row % layout.columns) * 13) % layout.columns;
}

function cubic(a: number, b: number, c: number, d: number, t: number) {
  const u = 1 - t; return u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * c + t * t * t * d;
}

/** One analytic identity; release and throat share their position and tangent. */
export function funnelParticle(id: number, seconds: number, rate: number, layout: FunnelLayout, visit: ParticleVisitor) {
  const age = seconds - id / rate;
  if (id < 1 || age > layout.redSeconds) return false;
  const row = Math.floor((id - 1) / layout.columns), offset = (id - 1) % layout.columns;
  const column = funnelColumn(id, layout);
  const side = layout.columns === 1 ? 0 : column / (layout.columns - 1) * 2 - 1;
  const startX = layout.columns === 1 ? layout.width / 2 : layout.left + column * layout.spacing;
  const endX = layout.width / 2 + side * layout.throatHalfWidth;
  const startY = layout.front + offset / rate * layout.feedSpeed;
  let x: number, y: number;
  if (age < -layout.pullSeconds) {
    const rowRelease = (row * layout.columns + 1) / rate - layout.pullSeconds;
    x = startX; y = layout.front + (seconds - rowRelease) * layout.feedSpeed;
  } else if (age < 0) {
    const p = 1 + age / layout.pullSeconds;
    // Individual departures loosen the strands without moving the source or
    // changing either endpoint's position/tangent. A single-column low-rate
    // comparison retains its straight path.
    const envelope = 16 * p * p * (1 - p) * (1 - p);
    const lateral = layout.columns > 1 ? (seed(id, 113) * 2 - 1) * Math.min(layout.spacing * .75, layout.width * .06) : 0;
    x = cubic(startX, startX, endX, endX, p) + lateral * envelope;
    y = cubic(startY, startY + layout.feedSpeed * layout.pullSeconds / 3,
      layout.throat - layout.exitSpeed * layout.pullSeconds / 3, layout.throat, p);
  } else {
    const p = age / layout.redSeconds;
    const fan = side * layout.width * .95 + (seed(id, 71) - .5) * layout.width * .12;
    x = cubic(endX, endX, layout.width / 2 + fan * .42, layout.width / 2 + fan, p);
    y = cubic(layout.throat, layout.throat + layout.exitSpeed * layout.redSeconds / 3,
      layout.height - (layout.height - layout.throat) * .2, layout.height + 3, p);
  }
  if (x < -3 || x > layout.width + 3 || y < layout.top || y > layout.height + 3) return false;
  visit(id, x, y, age >= 0); return true;
}

/** Complete, bounded age window; no sampling, recycling or per-point allocation. */
export function funnelParticles(seconds: number, rate: number, width: number, height: number, visit: ParticleVisitor, layout = funnelLayout(rate, width, height)) {
  const first = Math.max(1, Math.floor((seconds - layout.redSeconds) * rate));
  // Include the entire leading row. Ordinal clipping halfway through that row
  // would make holes at the upper edge even though its common y is visible.
  const last = Math.floor((seconds + layout.queueSeconds) * rate) + layout.columns;
  let count = 0;
  for (let id = first; id <= last; id++) if (funnelParticle(id, seconds, rate, layout, visit)) count++;
  return count;
}

/** Four fixed chunk positions; completed red chunks leave before reuse. */
export function gridParticles(seconds: number, rate: number, width: number, height: number, visit: ParticleVisitor) {
  const current = Math.floor(seconds / GRID_BATCH_SECONDS);
  const gap = width < 500 ? 14 : 26;
  const cellW = (width - gap) / 2, cellH = (height - gap) / 2;
  const firstBatch = Math.max(0, current - 3);
  const lastBatch = Math.max(3, current + 1);
  const emitted = Math.floor(seconds * rate + 1e-8);
  let count = 0;
  for (let batch = firstBatch; batch <= lastBatch; batch++) {
    const starts = batch * GRID_BATCH_SECONDS, retires = starts + 1;
    const arrival = batch < 4 ? 0 : starts - .08;
    if (seconds < arrival || seconds >= retires) continue;
    const entering = batch < 4 ? 0 : Math.max(0, (starts - seconds) / .08);
    const leaving = Math.max(0, (seconds - (retires - .08)) / .08);
    const slot = batch % 4;
    const cellLeft = (slot % 2) * (cellW + gap);
    // Incoming white and retiring red identities share only this reserved cell.
    // Complementary cell-width travel replaces a chunk without crossing a neighbor.
    const baseX = cellLeft + entering * cellW - leaving * cellW;
    const baseY = Math.floor(slot / 2) * (cellH + gap);
    const { first, last } = batchBounds(batch, rate), total = last - first + 1;
    const columns = Math.max(1, Math.floor(Math.sqrt(total * cellW / cellH)));
    const rows = Math.ceil(total / columns);
    const pitch = Math.min(cellW / columns, cellH / rows);
    const padX = (cellW - columns * pitch) / 2, padY = (cellH - rows * pitch) / 2;
    for (let id = first; id <= last; id++) {
      const index = id - first, row = Math.floor(index / columns), offset = index % columns;
      const column = row % 2 ? columns - 1 - offset : offset;
      const x = baseX + padX + (column + .5) * pitch;
      const y = baseY + padY + (row + .5) * pitch;
      if (x < cellLeft || x >= cellLeft + cellW) continue;
      visit(id, x, y, id <= emitted); count++;
    }
  }
  return count;
}
