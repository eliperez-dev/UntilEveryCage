import { describe, expect, it } from 'vitest';
import { SYNTHETIC_BASE, formatCount, scaleSteps } from '../../src/features/scale/scaleModel';

describe('synthetic scale model', () => {
  it('keeps bounded values explicit and derived from the base example', () => {
    expect(scaleSteps).toHaveLength(4);
    expect(scaleSteps.map((step) => step.estimate)).toEqual([1, 10, 100, 1000]);
    expect(scaleSteps.every((step) => step.uncertainty.includes('Illustrative range'))).toBe(true);
    expect(scaleSteps[0]?.estimate).toBe(SYNTHETIC_BASE);
  });

  it('formats model values without implying precision beyond the example', () => {
    expect(formatCount(1000)).toBe('1,000');
  });
});
