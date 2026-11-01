import { describe, expect, it } from 'vitest';
import { funnelLayout } from '../../src/app/scale-story/engine';
import { createFunnelOutflowPhysics } from '../../src/app/scale-story/funnelPhysics';

describe('optional complete-rate funnel outflow', () => {
  for (const rate of [2779, 65671]) it(`emits every identity at ${rate} per second with bounded finite visible state`, () => {
    const layout = funnelLayout(rate, 800, 500), physics = createFunnelOutflowPhysics(rate);
    physics.advance(0, layout);
    for (let frame = 1; frame <= 60; frame++) {
      physics.advance(frame / 60, layout);
      expect(physics.stats().emitted).toBe(Math.floor(frame / 60 * rate));
    }
    expect(physics.stats().materialized).toBe(rate);
    expect(physics.stats().alive + physics.stats().retired).toBe(rate);
    const points: number[][] = []; let valid = true;
    physics.visit((id,x,y,dead) => {
      valid &&= dead && Number.isSafeInteger(id) && [x,y].every(Number.isFinite)
        && x >= -3 && x <= 803 && y >= layout.throat && y <= 503;
      points.push([id,x,y]);
    });
    expect(points.length).toBeGreaterThan(0);
    expect(valid).toBe(true);
    expect(new Set(points.map(point => point[0])).size).toBe(points.length);
    physics.reset(); physics.advance(0, layout);
    for (let frame=1;frame<=60;frame++) physics.advance(frame / 60,layout);
    const repeated: number[][] = []; physics.visit((id,x,y) => repeated.push([id,x,y]));
    expect(repeated).toEqual(points);
  });

  it('seeks and resizes without replaying expired history or losing crossing totals', () => {
    const rate = 65671, physics = createFunnelOutflowPhysics(rate);
    physics.advance(1000000, funnelLayout(rate,800,500));
    expect(physics.stats().emitted).toBe(65671000000);
    expect(physics.stats().materialized).toBeLessThan(160000);
    physics.advance(1000000, funnelLayout(rate,320,430));
    expect(physics.stats().emitted).toBe(65671000000);
    expect(physics.stats().alive).toBeLessThan(physics.stats().capacity);
    physics.visit((_id,x,y) => { expect(Number.isFinite(x) && Number.isFinite(y)).toBe(true); });
  });
});
