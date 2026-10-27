import { recordCategoryKey, type ClassificationRecord } from './classificationSummary';

/** Editorial definitions, not facility observations. Only exact, structured
 * activity keys, documented source codes and affirmative flags select a subtype.
 * Never infer slaughter methods, current operation or laboratory use from a pin.
 * Reviewed 2026-10-27 against the primary references below. */
const REFERENCES = {
  awa: { label: 'APHIS classification guide', href: 'https://www.aphis.usda.gov/animal_welfare/downloads/graybook.pdf' },
  definitions: { label: 'Animal Welfare Act definitions', href: 'https://www.ecfr.gov/current/title-9/chapter-I/subchapter-A/part-1/section-1.1' },
  register: { label: 'APHIS source register', href: 'https://www.aphis.usda.gov/animal_welfare/downloads/List-of-Active-Licensees-and-Registrants.xlsx' },
  food: { label: 'Food establishment categories', href: 'https://data.food.gov.uk/codes/business/approved-food-establishments/sectors/MEAT' },
  products: { label: 'Animal-product establishment definitions', href: 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32004R0853' },
  aquaculture: { label: 'FAO aquaculture definition', href: 'https://www.fao.org/4/x6941e/x6941e04.htm' },
  slaughter: { label: 'Slaughter and animal welfare', href: 'https://www.gov.uk/government/publications/animal-welfare-report-202425/fsa-250906-animal-welfare-report-202425' },
  meatRequirements: { label: 'Meat establishment requirements', href: 'https://www.gov.uk/government/publications/legal-requirements-for-meat-establishments' },
  taxonomy: { label: 'Classification methodology', href: '#/about' },
} as const;
type ReferenceKey = keyof typeof REFERENCES;
type Template = Readonly<{ text: string; references: readonly ReferenceKey[] }>;
const entry = (text: string, ...references: ReferenceKey[]): Template => ({ text, references });

export const CLASSIFICATION_EXPLANATIONS = {
  animal_keeping_and_production: entry('Animal keeping and production covers raising, breeding or keeping animals for commercial use.', 'taxonomy'),
  slaughter: entry('Slaughterhouses are places where animals are killed for meat.', 'food'),
  processing_and_preparation: entry('Processing and preparation covers turning animal products into food, including cutting, cooking or packaging.', 'products'),
  research_and_animal_use: entry('This category covers the use of animals in research, testing or teaching.', 'definitions'),
  other_regulated_premises: entry('This category covers supporting businesses such as transport, storage, trade and other regulated premises.', 'taxonomy'),
  unclassified: entry('No recognised activity category has been assigned to this record.', 'taxonomy'),
  poultry_slaughter: entry('Poultry slaughter kills birds and prepares their bodies for food. Typical stages include bleeding, removing feathers and removing internal organs.', 'meatRequirements'),
  meat_slaughter: entry('Livestock slaughter covers killing farmed mammals and preparing their carcasses for food.', 'slaughter'),
  meat_processing: entry('Meat processing turns carcasses or meat into cuts, preparations or other meat products.', 'products'),
  poultry_processing: entry('Poultry processing prepares meat from birds for sale or further manufacture.', 'products'),
  fish_processing: entry('Fish processing prepares fish or shellfish for sale or manufacture into food products.', 'products'),
  dairy_processing: entry('Dairy processing turns milk into drinking milk, cheese or other dairy products.', 'products'),
  egg_processing: entry('Egg processing prepares eggs or egg contents for use in food products.', 'products'),
  cutting: entry('Cutting plants divide and debone meat from animals already slaughtered.', 'food', 'products'),
  processing: entry('Processing establishments prepare or manufacture food products from animal ingredients.', 'products'),
  animal_keeping: entry('Animal keeping covers premises used to house, rear or breed animals.', 'taxonomy'),
  animal_production: entry('Animal production covers raising animals or producing animal products such as milk and eggs.', 'taxonomy'),
  aquaculture: entry('Aquaculture is the farming of fish, shellfish or other aquatic animals.', 'aquaculture'),
  research: entry('Animal research facilities use or intend to use live animals in research, tests or experiments.', 'definitions'),
  animal_by_products: entry('Animal by-product premises handle animal bodies, parts or products outside the human food chain.', 'taxonomy'),
  logistics_and_storage: entry('Transport and storage businesses move, hold or distribute products between other facilities.', 'products'),
  cold_store: entry('Cold stores keep chilled or frozen animal products before they are distributed or processed.', 'products'),
  export: entry('This classification covers businesses registered to export animal products.', 'taxonomy'),
  general_food_business: entry('General food businesses handle, prepare or sell food; the classification does not specify a production activity.', 'taxonomy'),
  mixed_food_processing: entry('Mixed food processing combines ingredients into prepared food products.', 'taxonomy'),
  butcher_retail: entry('Retail butchers cut, prepare or sell meat to customers.', 'taxonomy'),
  fish_retail: entry('Fish retailers prepare or sell fish and seafood to customers.', 'taxonomy'),
  retail_and_prepared_food: entry('This category covers food retail and businesses preparing food for customers.', 'taxonomy'),
  commercial_food_business: entry('Commercial food businesses prepare, distribute or sell food.', 'taxonomy'),
  catering_and_institutional_kitchens: entry('Catering and institutional kitchens prepare meals for customers, organisations or institutions.', 'taxonomy'),
  food_contact_and_packaging: entry('These businesses make or handle packaging and materials used in contact with food.', 'taxonomy'),
  animal_products_adjacent: entry('These businesses support the handling, supply or sale of animal products.', 'taxonomy'),
  aphis_a: entry('APHIS Class A breeders sell animals bred and raised on their premises.', 'definitions'),
  aphis_b: entry('APHIS Class B dealers buy, resell or broker animals, including through auctions.', 'definitions'),
  aphis_c: entry('APHIS Class C exhibitors display animals to the public.', 'definitions'),
  aphis_f: entry('APHIS Class F identifies federal facilities using live animals in research or experiments.', 'definitions', 'register'),
  aphis_g: entry('APHIS Class G identifies agricultural animal-research facilities.', 'register'),
  aphis_h: entry('APHIS Class H intermediate handlers take custody of animals during commercial transport.', 'awa'),
  aphis_r: entry('APHIS Class R research facilities use or intend to use live animals in research, tests or experiments.', 'definitions'),
  aphis_t: entry('APHIS Class T carriers transport regulated animals for hire, including by road, air, rail or sea.', 'awa'),
  aphis_v: entry('APHIS Class V identifies Veterans Affairs animal-research facilities.', 'register'),
} as const satisfies Record<string, Template>;

export type ClassificationExplanationKey = keyof typeof CLASSIFICATION_EXPLANATIONS;
const exactActivityKeys = new Set<ClassificationExplanationKey>([
  'slaughter', 'meat_processing', 'fish_processing', 'dairy_processing', 'egg_processing', 'cutting', 'processing',
  'animal_keeping', 'animal_production', 'research', 'animal_by_products', 'logistics_and_storage', 'export',
  'general_food_business', 'mixed_food_processing', 'butcher_retail', 'fish_retail', 'retail_and_prepared_food',
  'commercial_food_business', 'catering_and_institutional_kitchens', 'food_contact_and_packaging', 'animal_products_adjacent',
]);
const poultrySpecies = new Set(['chicken', 'chickens', 'turkey', 'turkeys', 'duck', 'ducks', 'goose', 'geese', 'guinea', 'guineas', 'squab', 'squabs', 'poultry', 'ratite', 'ratites',
  'poultry_slaughter', 'chicken_slaughter', 'young_chicken_slaughter', 'mature_chicken_slaughter', 'turkey_slaughter', 'young_turkey_slaughter', 'mature_turkey_slaughter', 'duck_slaughter', 'goose_slaughter', 'geese_slaughter', 'guinea_slaughter', 'squab_slaughter', 'ratite_slaughter']);
const livestockSpecies = new Set(['cattle', 'calves', 'swine', 'hogs', 'pigs', 'sheep', 'lambs', 'goats', 'equine', 'horses', 'bison',
  'beef_cow_slaughter', 'bull_slaughter', 'steer_slaughter', 'heifer_slaughter', 'calf_slaughter', 'veal_calf_slaughter', 'swine_slaughter', 'hog_slaughter', 'sow_slaughter', 'sheep_slaughter', 'lamb_slaughter', 'goat_slaughter', 'equine_slaughter', 'horse_slaughter', 'bison_slaughter']);
const positive = (value: string | boolean) => value === true || (typeof value === 'string' && /^(?:yes|y|true|1)$/i.test(value.trim()));
const affirmativeKeys = (values: Readonly<Record<string, string | boolean>> | undefined) => Object.entries(values ?? {}).filter(([, value]) => positive(value)).map(([key]) => key.toLowerCase());
const aphisPriority = ['R', 'F', 'G', 'V', 'A', 'B', 'C', 'H', 'T'] as const;

/** Only US APHIS source-native fields establish an APHIS class. A matching
 * phrase in another source or a record name never selects one. */
export function aphisExplanationClasses(record: ClassificationRecord): string[] {
  if (record.sourceId !== 'us.aphis') return [];
  const terms = [record.sourceFacts?.nativeActivityLabel, record.sourceFacts?.nativeActivityCode, record.activitySource,
    ...(record.taxonomy?.assignments.flatMap(item => [item.sourceLabel, item.sourceCode]) ?? [])];
  const classes = new Set(terms.flatMap(term => [...(term ?? '').matchAll(/\bClass\s+([ABCFGHRTV])\b/gi)].map(match => match[1]!.toUpperCase())));
  return aphisPriority.filter(code => classes.has(code));
}

function subtype(record: ClassificationRecord): ClassificationExplanationKey {
  const primary = recordCategoryKey(record);
  const flags = affirmativeKeys(record.sourceFacts?.processingActivities);
  const species = affirmativeKeys(record.sourceFacts?.speciesSlaughtered);
  if (primary === 'slaughter' && species.length) {
    if (species.every(key => poultrySpecies.has(key))) return 'poultry_slaughter';
    if (species.every(key => livestockSpecies.has(key))) return 'meat_slaughter';
  }
  if (primary === 'animal_keeping_and_production' && ['no.fiskeridir.aquaculture', 'gb.scot.marine.aquaculture'].includes(record.sourceId ?? '')) return 'aquaculture';
  // These codes have an exact reviewed meaning in the European food approvals.
  const europeanSource = ['de.locations', 'it.853-2004', 'fsa_approved_establishments', 'fss_approved_establishments'].includes(record.sourceId ?? '');
  const codes = (record.taxonomy?.assignments ?? []).filter(item => item.status === 'mapped' || item.status === 'partial').flatMap(item => (item.sourceCode ?? '').split(';').map(code => code.trim().toUpperCase()));
  if (primary === 'other_regulated_premises' && europeanSource && codes.includes('CS')) return 'cold_store';
  if (primary === 'processing_and_preparation') {
    if (flags.some(key => ['poultry_processing', 'nrte_chicken_processing', 'rte_chicken_processing', 'nrte_poultry_processing', 'rte_poultry_processing'].includes(key))) return 'poultry_processing';
    if (flags.includes('meat_cutting')) return 'cutting';
  }
  const leaves = record.taxonomy?.leafActivities.map(item => item.key) ?? (record.category ? [record.category] : []);
  // Prefer a specific recognised activity within the displayed category.
  const compatible: Record<string, readonly string[]> = {
    slaughter: ['slaughter'], animal_keeping_and_production: ['animal_keeping', 'animal_production'],
    processing_and_preparation: ['meat_processing', 'poultry_processing', 'fish_processing', 'dairy_processing', 'egg_processing', 'cutting', 'mixed_food_processing', 'processing'],
    research_and_animal_use: ['research'], other_regulated_premises: ['animal_by_products', 'logistics_and_storage', 'export', 'butcher_retail', 'fish_retail', 'retail_and_prepared_food', 'commercial_food_business', 'catering_and_institutional_kitchens', 'food_contact_and_packaging', 'animal_products_adjacent', 'general_food_business'],
  };
  return (compatible[primary]?.find(key => leaves.includes(key) && exactActivityKeys.has(key as ClassificationExplanationKey)) as ClassificationExplanationKey | undefined) ?? primary;
}

export function classificationExplanation(record: ClassificationRecord, translate: (text: string) => string = text => text, locale = 'en') {
  const classes = aphisExplanationClasses(record);
  const nativeLabels = [record.sourceFacts?.nativeActivityLabel, record.activitySource, ...(record.taxonomy?.assignments.map(item => item.sourceLabel) ?? [])].filter(Boolean).join('; ');
  // The public guide does not define the legacy G/V courtesy codes. Explain
  // those only when the full source-native designation establishes the type.
  const classKey = (code: string): ClassificationExplanationKey => {
    if (code === 'G' && !/\bClass\s+G\b[^;]*Agricultural Research/i.test(nativeLabels)) return 'research';
    if (code === 'V' && !/\bClass\s+V\b[^;]*(?:Veteran(?:'?s)?(?: Affairs| Administration)?|VA)\s+Hospital/i.test(nativeLabels)) return 'research';
    return `aphis_${code.toLowerCase()}` as ClassificationExplanationKey;
  };
  const keys = classes.length ? [...new Set(classes.map(classKey))].slice(0, 2) : [subtype(record)];
  const templates = keys.map(key => CLASSIFICATION_EXPLANATIONS[key]);
  const references: Array<{ label: string; href: string }> = [...new Set(templates.flatMap(template => template.references))].map(key => REFERENCES[key]);
  let fact = '';
  if (keys.length === 1 && ['aphis_r', 'aphis_f', 'aphis_g', 'aphis_v', 'research'].includes(keys[0]!)) {
    const reports = (record.sourceFacts?.aphisAnnualReports ?? []).filter(report => /^\d{4}$/.test(report.fiscalYear)
      && report.speciesCounts.length > 0 && report.speciesCounts.every(item => Number.isSafeInteger(item.count) && item.count >= 0)
      && new Set(report.speciesCounts.map(item => item.species.toLowerCase().trim())).size === report.speciesCounts.length
      && report.safeProvenance.sourceId === 'us.aphis.annual-reports' && report.safeProvenance.evidenceType === 'annual_reports'
      && report.safeProvenance.matchMethod === 'exact_source_identifier' && report.safeProvenance.matchedIdentifierTypes.length > 0)
      .sort((a, b) => b.fiscalYear.localeCompare(a.fiscalYear));
    // More than one report for the latest year is ambiguous; do not choose one.
    const latest = reports[0];
    if (latest && reports.filter(report => report.fiscalYear === latest.fiscalYear).length === 1) {
      const total = latest.speciesCounts.reduce((sum, item) => sum + item.count, 0);
      if (Number.isSafeInteger(total)) {
        fact = translate('The fiscal year {year} report lists {count} animals across the reported species.').replace('{year}', latest.fiscalYear).replace('{count}', new Intl.NumberFormat(locale).format(total));
        try { const url = new URL(latest.sourceUrl); if (url.protocol === 'https:') references.push({ label: 'Source report', href: url.href }); } catch { /* Source facts remain available separately. */ }
      }
    }
  }
  return {
    keys,
    text: [...templates.map(template => translate(template.text)), fact].filter(Boolean).join(' '),
    references,
  };
}
