import { describe, expect, it } from 'vitest';
import { CATEGORY_PRESENTATIONS, CATEGORY_VISUAL_CHANNELS, categoryPresentation } from '../../src/features/locations/categoryPresentation';

describe('category presentation seam', () => {
  it('exposes the audited compact vocabulary and neutral fallback', () => {
    expect(Object.keys(CATEGORY_PRESENTATIONS)).toEqual([
      'animal_production', 'slaughter', 'processing', 'research', 'other_regulated', 'unclassified',
    ]);
    expect(categoryPresentation('not-yet-mapped')).toBe(CATEGORY_PRESENTATIONS.unclassified);
  });

  it('keeps category separate from density, precision, selection, and confidence', () => {
    expect(CATEGORY_VISUAL_CHANNELS).toEqual({
      clusters: 'category-neutral', precision: 'independent', selection: 'independent', confidence: 'independent',
    });
  });
});
