import { describe, expect, it } from 'vitest';
import { precisionPresentation } from '../../src/features/locations/precisionPresentation';

describe('public location precision labels', () => {
  it('does not present source-reported or approximate locations as exact', () => {
    expect(precisionPresentation('source_reported')).toBe('Source-provided coordinates');
    expect(precisionPresentation('approximate')).toBe('Approximate location');
    expect(precisionPresentation('exact')).toBe('Exact public point');
  });

  it('labels city, unmapped, and unknown values explicitly', () => {
    expect(precisionPresentation('city')).toBe('City-level approximation');
    expect(precisionPresentation('provider_locality_approximate')).toBe('City-level approximation');
    expect(precisionPresentation('unmapped')).toMatch(/no public point/);
    expect(precisionPresentation('future_precision')).toBe('Location precision unavailable');
  });
});
