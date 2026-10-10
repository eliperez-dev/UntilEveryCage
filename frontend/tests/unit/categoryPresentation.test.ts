import { describe, expect, it } from 'vitest';
import { CATEGORY_PRESENTATIONS, CATEGORY_PRIMARY_BY_SOURCE_KEY, CATEGORY_VISUAL_CHANNELS, categoryPresentation } from '../../src/features/locations/categoryPresentation';

describe('category presentation seam', () => {
  it('exposes the audited compact vocabulary and neutral fallback', () => {
    expect(Object.keys(CATEGORY_PRESENTATIONS)).toEqual([
      'animal_keeping_and_production', 'slaughter', 'processing_and_preparation', 'research_and_animal_use', 'other_regulated_premises', 'unclassified',
    ]);
    expect(categoryPresentation('not-yet-mapped')).toBe(CATEGORY_PRESENTATIONS.unclassified);
    expect(categoryPresentation('animal_production')).toBe(CATEGORY_PRESENTATIONS.animal_keeping_and_production);
    expect(categoryPresentation('fish_processing')).toBe(CATEGORY_PRESENTATIONS.processing_and_preparation);
    expect(CATEGORY_PRIMARY_BY_SOURCE_KEY.fish_processing).toBe('processing_and_preparation');
  });

  it('keeps category separate from density, precision, selection, and confidence', () => {
    expect(CATEGORY_VISUAL_CHANNELS).toEqual({
      clusters: 'category-neutral', precision: 'independent', selection: 'independent', confidence: 'independent',
    });
  });

  it('gives each primary category a distinct shape and an accessible label', () => {
    const shapes = Object.values(CATEGORY_PRESENTATIONS).map(item => item.shape);
    expect(new Set(shapes).size).toBe(6);
    expect(Object.values(CATEGORY_PRESENTATIONS).every(item => item.label.length > 0 && item.color.startsWith('#'))).toBe(true);
  });
});
