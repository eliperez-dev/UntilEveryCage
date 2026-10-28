import { describe, expect, it } from 'vitest';
import { ActiveStoryClock, batchBounds, CHICKEN_LINE_RATE, funnelParticles, gridParticles, lineParticles, seed, snakePosition, STORY_RATES } from '../../src/app/scale-story/engine';
import { FISH_2019, LAND_ANIMALS_2024, litresForIndividuals, oneSecondEachYears, poolsForIndividuals, populationDays, REFERENCE_POOL_LITRES } from '../../src/app/scale-story/comparisons';

describe('active story time', () => {
  it('preserves fractional throughput across frame sizes without per-frame rounding', () => {
    const fine = new ActiveStoryClock(), coarse = new ActiveStoryClock();
    fine.setRunning(true, 0); coarse.setRunning(true, 0);
    for (let time = 10; time <= 10000; time += 10) fine.advance(time);
    coarse.advance(10000);
    expect(fine.emitted(STORY_RATES.land)).toBe(27790);
    expect(fine.emitted(STORY_RATES.fish)).toBe(coarse.emitted(STORY_RATES.fish));
    expect(fine.emitted(STORY_RATES.fish)).toBe(656710);
  });
  it('excludes paused, offscreen and hidden time and resumes without catchup', () => {
    const clock = new ActiveStoryClock(); clock.setRunning(true, 0); clock.advance(500);
    clock.setRunning(false, 600); clock.advance(300000); clock.setRunning(true, 400000); clock.advance(400400);
    expect(clock.elapsed).toBeCloseTo(1);
    expect(clock.emitted(2779)).toBe(2779);
  });
  it('handles low frame rates analytically and never counts backwards', () => {
    const clock = new ActiveStoryClock(); clock.setRunning(true, 100); clock.advance(3100); clock.advance(3000);
    expect(clock.emitted(2779)).toBe(8337);
    clock.advance(4100); expect(clock.emitted(2779)).toBe(11116);
  });
  it('accounts for exactly 140 chickens and 120 people over 60 active seconds', () => {
    const clock = new ActiveStoryClock(); clock.setRunning(true, 0);
    for (let now = 0; now <= 60000; now += 17) clock.advance(now);
    clock.advance(60000);
    expect(clock.emitted(CHICKEN_LINE_RATE)).toBe(140);
    expect(clock.emitted(2)).toBe(120);
  });
});

describe('individual dot identity', () => {
  it('allocates adjacent quarter-second chunks with no missing or duplicated animal', () => {
    for (const rate of Object.values(STORY_RATES)) {
      let next = 1;
      for (let batch = 0; batch < 400; batch++) {
        const bounds = batchBounds(batch, rate); expect(bounds.first).toBe(next); next = bounds.last + 1;
      }
      expect(next - 1).toBe(rate * 100);
    }
  });
  it('snakes across alternate rows while preserving each ordinal through layout changes', () => {
    expect(Array.from({ length: 8 }, (_, index) => snakePosition(index, 4))).toEqual([
      { column: 0, row: 0 }, { column: 1, row: 0 }, { column: 2, row: 0 }, { column: 3, row: 0 },
      { column: 3, row: 1 }, { column: 2, row: 1 }, { column: 1, row: 1 }, { column: 0, row: 1 },
    ]);
    for (const columns of [7, 53, 91]) for (let index = 0; index < 1000; index++) {
      const { row, column } = snakePosition(index, columns);
      expect(row * columns + (row % 2 ? columns - 1 - column : column)).toBe(index);
    }
  });
  it('never revives a visible completed dot during chunk handoffs', () => {
    const dead = new Set<number>();
    let duplicates = false, revived = false, minimum = Infinity, maximum = 0;
    for (let frame = 0; frame < 160; frame++) {
      const seen = new Set<number>();
      const count = gridParticles(frame / 50, 2779, 320, 650, (id, _x, _y, killed) => {
        if (seen.has(id)) duplicates = true; seen.add(id);
        if (dead.has(id) && !killed) revived = true;
        if (killed) dead.add(id);
      });
      minimum = Math.min(minimum, count); maximum = Math.max(maximum, count);
    }
    expect(duplicates).toBe(false); expect(revived).toBe(false);
    expect(minimum).toBeGreaterThan(1300); expect(maximum).toBeLessThanOrEqual(5 * Math.ceil(2779 / 4));
  });
  it('keeps fish work bounded after arbitrarily long active periods', () => {
    for (const seconds of [1.98, 1000.97, 1000000.24]) {
      const ids = new Set<number>();
      let duplicates = false;
      const count = funnelParticles(seconds, STORY_RATES.fish, 272, 500, id => { if (ids.has(id)) duplicates = true; ids.add(id); });
      expect(duplicates).toBe(false);
      expect(count).toBeLessThan(160000); expect(count).toBeGreaterThan(10000);
      expect(gridParticles(seconds, STORY_RATES.fish, 272, 650, () => {})).toBeLessThanOrEqual(5 * Math.ceil(STORY_RATES.fish / 4));
    }
  });
  it('keeps incoming and retiring chunks inside their own cell throughout handoffs', () => {
    const width = 900, height = 570, gap = 26, cellW = (width - gap) / 2, cellH = (height - gap) / 2;
    let violations = 0;
    for (const seconds of [.93, .97, .99, 1.18, 1.24, 1.46, 1.73, 2.98]) {
      gridParticles(seconds, STORY_RATES.land, width, height, (id, x, y) => {
        const slot = (Math.ceil(id / (STORY_RATES.land * .25)) - 1) % 4;
        const left = (slot % 2) * (cellW + gap), top = Math.floor(slot / 2) * (cellH + gap);
        if (x < left || x >= left + cellW || y < top || y >= top + cellH) violations++;
      });
    }
    expect(violations).toBe(0);
  });
  it('turns the same queued individual red at the throat and scatters deterministic identities', () => {
    const positions = new Map<number, { x: number; y: number; dead: boolean }>();
    funnelParticles(.1, 2779, 1000, 500, (id, x, y, dead) => positions.set(id, { x, y, dead }));
    expect(positions.get(1000)?.dead).toBe(false);
    funnelParticles(1000 / 2779, 2779, 1000, 500, (id, x, y, dead) => { if (id === 1000) positions.set(id, { x, y, dead }); });
    expect(positions.get(1000)).toEqual({ x: 500, y: 265, dead: true });
    expect(seed(1000, 23)).toBe(seed(1000, 23)); expect(seed(1000, 23)).not.toBe(seed(1001, 23));
    const resized = new Map<number, boolean>();
    funnelParticles(.4, 2779, 320, 500, (id, _x, _y, dead) => resized.set(id, dead));
    expect(resized.get(1000)).toBe(true);
  });
  it('uses the same individual-state model for the two-per-second human comparison', () => {
    const clock = new ActiveStoryClock(); clock.setRunning(true, 0); clock.advance(1750);
    expect(clock.emitted(2)).toBe(3);
    const alive = new Map<number, boolean>(), after = new Map<number, boolean>();
    funnelParticles(.7, 2, 100, 500, (id, _x, _y, dead) => alive.set(id, dead));
    funnelParticles(1.1, 2, 100, 500, (id, _x, _y, dead) => after.set(id, dead));
    expect(alive.get(2)).toBe(false); expect(after.get(2)).toBe(true);
  });
  it('changes a chicken identity only when it crosses the labelled horizontal line', () => {
    const id = 4, crossing = id / CHICKEN_LINE_RATE, height = 350;
    const states = new Map<number, { y: number; dead: boolean }>();
    lineParticles(crossing - .1, CHICKEN_LINE_RATE, 125, height, (particle, _x, y, dead) => states.set(particle, { y, dead }));
    expect(states.get(id)?.dead).toBe(false); expect(states.get(id)!.y).toBeLessThan(height * .48);
    lineParticles(crossing, CHICKEN_LINE_RATE, 125, height, (particle, _x, y, dead) => states.set(particle, { y, dead }));
    expect(states.get(id)).toEqual({ y: height * .48, dead: true });
    lineParticles(crossing + .2, CHICKEN_LINE_RATE, 125, height, (particle, _x, y, dead) => states.set(particle, { y, dead }));
    expect(states.get(id)?.dead).toBe(true); expect(states.get(id)!.y).toBeGreaterThan(height * .48);
    expect(lineParticles(1000000, CHICKEN_LINE_RATE, 125, height, () => {})).toBeLessThan(12);
  });
});

describe('sourced representational comparisons', () => {
  it('converts faucet millilitres to litres and reference pools', () => {
    expect(litresForIndividuals(4000)).toBe(1);
    expect(REFERENCE_POOL_LITRES).toBe(3125000);
    expect(litresForIndividuals(LAND_ANIMALS_2024)).toBeCloseTo(21973069.36975);
    expect(poolsForIndividuals(LAND_ANIMALS_2024)).toBeCloseTo(7.03138219832);
    expect(FISH_2019.map(litresForIndividuals)).toEqual([264500000, 517750000]);
    expect(FISH_2019.map(poolsForIndividuals)).toEqual([84.64, 165.68]);
  });
  it('compares counts with the dated UN population benchmark, not human deaths', () => {
    expect(populationDays(LAND_ANIMALS_2024, 366)).toBeCloseTo(34.1463447);
    expect(populationDays(FISH_2019[0], 365)).toBeCloseTo(2.8298677);
    expect(populationDays(FISH_2019[1], 365)).toBeCloseTo(1.4451956);
    expect(oneSecondEachYears(LAND_ANIMALS_2024)).toBeCloseTo(2785.2, 0);
  });
});
