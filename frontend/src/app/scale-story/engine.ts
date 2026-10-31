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

/** A finite analytic age window. Every emitted identity in that window is visited. */
export function funnelParticles(seconds: number, rate: number, width: number, height: number, visit: ParticleVisitor) {
  const first = Math.max(1, Math.floor((seconds - FUNNEL_RED_SECONDS) * rate));
  const last = Math.floor((seconds + FUNNEL_QUEUE_SECONDS) * rate);
  const throat = height * .53;
  let count = 0;
  for (let id = first; id <= last; id++) {
    const age = seconds - id / rate;
    const side = seed(id, 23) * 2 - 1;
    let x: number, y: number;
    if (age < 0) {
      // Whole quarter-second chunks enter the queue together, then narrow.
      const birth = Math.floor((id / rate) / .25) * .25 - .95;
      if (seconds < birth) continue;
      const queue = Math.min(1, -age / FUNNEL_QUEUE_SECONDS);
      x = width / 2 + side * width * (.014 + .44 * Math.pow(queue, 1.45));
      y = throat - Math.pow(queue, .78) * (throat - 13);
    } else {
      const lifetime = .63 + seed(id, 71) * .37;
      if (age > lifetime) continue;
      x = width / 2 + side * width * 1.25 * age / lifetime;
      y = throat + height * (.57 + seed(id, 53) * .48) * age / lifetime + height * .22 * age * age;
    }
    if (x < -3 || x > width + 3 || y < -3 || y > height + 3) continue;
    visit(id, x, y, age >= 0); count++;
  }
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
