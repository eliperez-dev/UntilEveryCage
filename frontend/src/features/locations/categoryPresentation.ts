/**
 * Presentation vocabulary approved by the classification audit.
 *
 * Source activity strings are deliberately not mapped here. The current
 * import/API collapses multi-activity evidence, so assigning those strings to
 * a primary category would imply a conclusion the data contract cannot yet
 * support. Consumers must use `unclassified` until the backend supplies one
 * of these stable keys explicitly.
 */
export const CATEGORY_PRESENTATIONS = Object.freeze({
  animal_production: Object.freeze({ label: 'Animal keeping / production', color: '#009E73', shape: 'circle' }),
  slaughter: Object.freeze({ label: 'Slaughter', color: '#D55E00', shape: 'diamond' }),
  processing: Object.freeze({ label: 'Processing / preparation', color: '#0072B2', shape: 'square' }),
  research: Object.freeze({ label: 'Research / animal use', color: '#CC79A7', shape: 'hexagon' }),
  other_regulated: Object.freeze({ label: 'Other regulated premises', color: '#E69F00', shape: 'triangle' }),
  unclassified: Object.freeze({ label: 'Unclassified', color: '#B8B8B8', shape: 'outlined-circle' }),
} as const);

export type CategoryPresentationKey = keyof typeof CATEGORY_PRESENTATIONS;

export function categoryPresentation(key: string | null | undefined) {
  return key && key in CATEGORY_PRESENTATIONS
    ? CATEGORY_PRESENTATIONS[key as CategoryPresentationKey]
    : CATEGORY_PRESENTATIONS.unclassified;
}

export const CATEGORY_VISUAL_CHANNELS = Object.freeze({
  clusters: 'category-neutral',
  precision: 'independent',
  selection: 'independent',
  confidence: 'independent',
} as const);
