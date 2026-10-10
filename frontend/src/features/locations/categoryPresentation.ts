/** Stable taxonomy keys to restrained colors and color-independent shapes. */
export const CATEGORY_PRESENTATIONS = Object.freeze({
  animal_keeping_and_production: Object.freeze({ label: 'Animal keeping and production', color: '#009E73', shape: 'circle' }),
  slaughter: Object.freeze({ label: 'Slaughter', color: '#D55E00', shape: 'diamond' }),
  processing_and_preparation: Object.freeze({ label: 'Processing and preparation', color: '#0072B2', shape: 'square' }),
  research_and_animal_use: Object.freeze({ label: 'Research and animal use', color: '#CC79A7', shape: 'hexagon' }),
  other_regulated_premises: Object.freeze({ label: 'Other regulated premises', color: '#E69F00', shape: 'triangle' }),
  unclassified: Object.freeze({ label: 'Unclassified', color: '#B8B8B8', shape: 'outlined-circle' }),
} as const);

export type CategoryPresentationKey = keyof typeof CATEGORY_PRESENTATIONS;

// Older preview fixtures and third-party consumers may still send the short
// V1-compatible keys. Resolve them for display without changing API values.
const LEGACY_CATEGORY_KEYS: Readonly<Record<string, CategoryPresentationKey>> = Object.freeze({
  animal_production: 'animal_keeping_and_production',
  farm: 'animal_keeping_and_production',
  processing: 'processing_and_preparation',
  research: 'research_and_animal_use',
  laboratory: 'research_and_animal_use',
  other_regulated: 'other_regulated_premises',
  dealer: 'other_regulated_premises',
  exhibitor: 'other_regulated_premises',
  meat_processing: 'processing_and_preparation',
  fish_processing: 'processing_and_preparation',
  dairy_processing: 'processing_and_preparation',
  egg_processing: 'processing_and_preparation',
  mixed_food_processing: 'processing_and_preparation',
  cutting: 'processing_and_preparation',
  logistics_and_storage: 'other_regulated_premises',
  animal_products_adjacent: 'other_regulated_premises',
  general_food_business: 'other_regulated_premises',
  butcher_retail: 'other_regulated_premises',
  fish_retail: 'other_regulated_premises',
  retail_and_prepared_food: 'other_regulated_premises',
  commercial_food_business: 'other_regulated_premises',
  catering_and_institutional_kitchens: 'other_regulated_premises',
  food_contact_and_packaging: 'other_regulated_premises',
  animal_keeping: 'animal_keeping_and_production',
});

/** Explicit, source-backed compatibility keys for map paint expressions. */
export const CATEGORY_PRIMARY_BY_SOURCE_KEY: Readonly<Record<string, CategoryPresentationKey>> = Object.freeze({
  ...Object.fromEntries(Object.keys(CATEGORY_PRESENTATIONS).map((key) => [key, key as CategoryPresentationKey])),
  ...LEGACY_CATEGORY_KEYS,
});

export function categoryPresentation(key: string | null | undefined) {
  const normalized = key ? LEGACY_CATEGORY_KEYS[key] ?? key : undefined;
  return normalized && normalized in CATEGORY_PRESENTATIONS
    ? CATEGORY_PRESENTATIONS[normalized as CategoryPresentationKey]
    : CATEGORY_PRESENTATIONS.unclassified;
}

export const CATEGORY_VISUAL_CHANNELS = Object.freeze({
  clusters: 'category-neutral',
  precision: 'independent',
  selection: 'independent',
  confidence: 'independent',
} as const);
