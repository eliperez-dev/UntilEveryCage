import { describe, expect, it } from 'vitest';
import { CATEGORY_PRESENTATIONS, CATEGORY_PRIMARY_BY_SOURCE_KEY, CATEGORY_VISUAL_CHANNELS, CATEGORY_PIN_COLORS, CATEGORY_PIN_IMAGES, categoryPresentation } from '../../src/features/locations/categoryPresentation';

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

  it('uses graphite for Processing, ochre for keeping and grey for Unclassified', () => {
    expect(CATEGORY_PRESENTATIONS.processing_and_preparation.color).toBe('#515B60');
    expect(CATEGORY_PIN_IMAGES.processing_and_preparation).toBe('v1-pin-graphite');
    expect(CATEGORY_PRESENTATIONS.animal_keeping_and_production.color).toBe('#D5B84A');
    expect(CATEGORY_PIN_IMAGES.animal_keeping_and_production).toBe('v1-pin-yellow');
    expect(CATEGORY_PRESENTATIONS.unclassified.color).toBe('#B8B8B8');
    expect(CATEGORY_PIN_COLORS.unclassified).toBe('grey');
    expect(Object.values(CATEGORY_PIN_COLORS).filter(color => color === 'grey')).toHaveLength(1);
    expect(new Set(Object.values(CATEGORY_PIN_COLORS)).size).toBe(6);
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
