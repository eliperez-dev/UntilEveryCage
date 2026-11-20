import { describe, expect, it } from 'vitest';
import { ActiveStoryClock, CHICKEN_LINE_RATE, FUNNEL_QUEUE_SECONDS, FUNNEL_RED_SECONDS, funnelColumn, funnelLayout, funnelParticle, funnelParticles, lineParticles, seed, STORY_RATES } from '../../src/app/scale-story/engine';
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
  it('turns the same queued individual red at the throat and scatters deterministic identities', () => {
    const positions = new Map<number, { x: number; y: number; dead: boolean }>();
    funnelParticles(.1, 2779, 1000, 500, (id, x, y, dead) => positions.set(id, { x, y, dead }));
    expect(positions.get(1000)?.dead).toBe(false);
    funnelParticles(1000 / 2779, 2779, 1000, 500, (id, x, y, dead) => { if (id === 1000) positions.set(id, { x, y, dead }); });
    const layout = funnelLayout(2779, 1000, 500);
    const side = funnelColumn(1000, layout) / (layout.columns - 1) * 2 - 1;
    expect(positions.get(1000)).toEqual({ x: 500 + side * layout.throatHalfWidth, y: 350, dead: true });
    expect(seed(1000, 23)).toBe(seed(1000, 23)); expect(seed(1000, 23)).not.toBe(seed(1001, 23));
    const resized = new Map<number, boolean>();
    funnelParticles(.4, 2779, 320, 500, (id, _x, _y, dead) => resized.set(id, dead));
    expect(resized.get(1000)).toBe(true);
  });
  it('permutes every source row bijectively without sorting its crossing order across the grid', () => {
    for (const rate of Object.values(STORY_RATES)) for (const width of [272, 1000]) {
      const layout = funnelLayout(rate, width, 570);
      for (const row of [0, 1, 29, 100000]) {
        const columns = Array.from({ length: layout.columns }, (_, offset) => funnelColumn(row * layout.columns + offset + 1, layout));
        expect(new Set(columns).size).toBe(layout.columns);
        expect(Math.min(...columns)).toBe(0); expect(Math.max(...columns)).toBe(layout.columns - 1);
        expect(columns.slice(1).some((column, index) => Math.abs(column - columns[index]!) > 1)).toBe(true);
      }
      expect(layout.rowSeconds).toBe(layout.columns / rate);
      expect(layout.spacing).toBeGreaterThanOrEqual(rate === STORY_RATES.fish ? 2.5 : 8.4);
    }
  });
  it('keeps distant source points in complete, equally spaced rows and columns at both real rates', () => {
    let violations = 0, fullRows = 0;
    for (const rate of Object.values(STORY_RATES)) for (const width of [272, 1000]) {
      const layout = funnelLayout(rate, width, 570), rows = new Map<number, Set<number>>();
      funnelParticles(5.137, rate, width, 570, (id, x, y, dead) => {
        if (dead || 5.137 - id / rate >= -layout.pullSeconds || y < layout.top || y >= layout.front - layout.spacing) return;
        const row = Math.floor((id - 1) / layout.columns), column = funnelColumn(id, layout);
        const expectedY = layout.front + (5.137 - ((row * layout.columns + 1) / rate - layout.pullSeconds)) * layout.feedSpeed;
        if (Math.abs(x - (layout.left + column * layout.spacing)) > 1e-8 || Math.abs(y - expectedY) > 1e-8) violations++;
        const members = rows.get(row) ?? new Set(); members.add(column); rows.set(row, members);
      }, layout);
      for (const columns of rows.values()) { fullRows++; if (columns.size !== layout.columns) violations++; }
    }
    expect(violations).toBe(0); expect(fullRows).toBeGreaterThan(30);
  });
  it('preserves each identity and position through release and the exact id/rate throat crossing', () => {
    const lateralOffsets = new Set<number>();
    for (const rate of [2, STORY_RATES.land, STORY_RATES.fish]) for (const width of [272, 1000]) {
      const layout = funnelLayout(rate, width, 570), id = Math.ceil(rate * 3.37), crossing = id / rate;
      const sample = (time: number) => {
        let result: { id: number; x: number; y: number; dead: boolean } | undefined;
        funnelParticle(id, time, rate, layout, (particle, x, y, dead) => { result = { id: particle, x, y, dead }; });
        expect(result).toBeDefined(); return result!;
      };
      const epsilon = 1e-7, release = crossing - layout.pullSeconds;
      const beforeRelease = sample(release - epsilon), afterRelease = sample(release + epsilon);
      expect(Math.hypot(beforeRelease.x - afterRelease.x, beforeRelease.y - afterRelease.y)).toBeLessThan(.01);
      expect(Math.abs(afterRelease.x - beforeRelease.x) / epsilon).toBeLessThan(.1);
      if (layout.columns > 1) {
        const midpoint = sample(crossing - layout.pullSeconds / 2);
        const column = funnelColumn(id, layout), side = column / (layout.columns - 1) * 2 - 1;
        const straightMidpoint = (layout.left + column * layout.spacing + layout.width / 2 + side * layout.throatHalfWidth) / 2;
        const offset = (midpoint.x - straightMidpoint) / layout.spacing;
        expect(Math.abs(offset)).toBeLessThanOrEqual(.750001);
        expect(Math.abs(offset)).toBeGreaterThan(.00001);
        lateralOffsets.add(Math.round(offset * 1000000));
      }
      const before = sample(crossing - epsilon), exact = sample(crossing), after = sample(crossing + epsilon);
      expect(before.dead).toBe(false); expect(exact.dead).toBe(true); expect(after.dead).toBe(true);
      expect(exact.id).toBe(id); expect(exact.y).toBe(layout.throat);
      expect(Math.hypot(before.x - after.x, before.y - after.y)).toBeLessThan(.01);
      expect(Math.abs((exact.x - before.x) / epsilon - (after.x - exact.x) / epsilon)).toBeLessThan(.1);
      expect(Math.abs((exact.y - before.y) / epsilon - (after.y - exact.y) / epsilon)).toBeLessThan(.1);
    }
    expect(lateralOffsets.size).toBeGreaterThan(1);
  });
  it('keeps every crossing identity, bounded windows and death state through resize and long runtimes', () => {
    for (const rate of Object.values(STORY_RATES)) for (const seconds of [0, 1.68, 30.137, 1000000.24]) {
      const states = new Map<number, boolean>();
      const wide = funnelLayout(rate, 1000, 570), narrow = funnelLayout(rate, 272, 490);
      for (const layout of [wide, narrow]) {
        expect(layout.queueSeconds).toBeLessThanOrEqual(FUNNEL_QUEUE_SECONDS);
        expect(layout.redSeconds).toBeLessThanOrEqual(FUNNEL_RED_SECONDS);
        const ids = new Set<number>(); let invalid = false;
        const count = funnelParticles(seconds, rate, layout.width, layout.height, (id, x, y, dead) => {
          if (id < 1 || ids.has(id) || !Number.isFinite(x) || !Number.isFinite(y) || dead !== (seconds >= id / rate)) invalid = true;
          if (states.has(id) && states.get(id) !== dead) invalid = true;
          ids.add(id); states.set(id, dead);
        }, layout);
        expect(invalid).toBe(false); expect(count).toBeLessThan(160000);
        expect(count).toBeLessThanOrEqual(Math.ceil(rate * (layout.queueSeconds + layout.redSeconds)) + layout.columns + 2);
        // Every individual crossing within this interval is visible; density never samples IDs.
        for (let id = Math.max(1, Math.ceil((seconds - .001) * rate)); id <= Math.floor((seconds + .001) * rate); id++) expect(ids.has(id)).toBe(true);
      }
    }
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
