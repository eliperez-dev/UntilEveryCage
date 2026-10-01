export const TAXONOMY_VERSION = 'uec-taxonomy-v1' as const;

export const TAXONOMY_PRIMARY_KEYS = [
  'animal_keeping_and_production',
  'slaughter',
  'processing_and_preparation',
  'research_and_animal_use',
  'other_regulated_premises',
  'unclassified',
] as const;

export type TaxonomyPrimaryKey = (typeof TAXONOMY_PRIMARY_KEYS)[number];
export type TaxonomyMethod = 'direct' | 'derived' | 'candidate';
export type TaxonomyStatus = 'mapped' | 'partial' | 'unmapped' | 'unclassified' | 'conflicting' | 'ambiguous';

export type TaxonomyLeafActivity = Readonly<{ key: string; label: string }>;
export type TaxonomyAssignment = Readonly<{
  primaryKey: TaxonomyPrimaryKey;
  leafKey: string | null;
  leafLabel: string | null;
  sourceCodeReference: string | null;
  sourceLabelReference: string | null;
  sourceCode: string | null;
  sourceLabel: string | null;
  method: TaxonomyMethod;
  status: TaxonomyStatus;
  taxonomyVersion: string;
  crosswalkVersion: string | null;
  rulesetVersion: string | null;
  observationId: string | null;
  sourceRecordId: string | null;
  artifactId: string | null;
}>;

export type TaxonomyClassification = Readonly<{
  displayCategory: TaxonomyPrimaryKey;
  primaryCategories: readonly TaxonomyPrimaryKey[];
  leafActivities: readonly TaxonomyLeafActivity[];
  assignments: readonly TaxonomyAssignment[];
  taxonomyVersion: string;
}>;

export const isTaxonomyPrimaryKey = (value: unknown): value is TaxonomyPrimaryKey =>
  typeof value === 'string' && (TAXONOMY_PRIMARY_KEYS as readonly string[]).includes(value);

const METHODS: readonly string[] = ['direct', 'derived', 'candidate'];
const STATUSES: readonly string[] = ['mapped', 'partial', 'unmapped', 'unclassified', 'conflicting', 'ambiguous'];

function safeText(value: unknown, field: string): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'string' || value.length > 500) throw new TypeError(`Invalid taxonomy ${field}.`);
  return value;
}

/** Parses only the allowlisted taxonomy fields; unknown primary keys fail safe to unclassified. */
export function parseTaxonomyClassification(value: unknown): TaxonomyClassification | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError('Invalid taxonomy payload.');
  const row = value as Record<string, unknown>;
  const present = ['taxonomy_display_category', 'taxonomy_primary_categories', 'taxonomy_leaf_activities', 'taxonomy_assignments']
    .some(key => row[key] !== undefined);
  if (!present) return undefined;

  const rawCategories = row.taxonomy_primary_categories;
  if (rawCategories !== undefined && (!Array.isArray(rawCategories) || rawCategories.length > 32 || !rawCategories.every(key => typeof key === 'string'))) {
    throw new TypeError('Invalid taxonomy primary categories.');
  }
  const categorySource = rawCategories as string[] | undefined;
  const primaryCategories = [...new Set((categorySource?.length ? categorySource : [row.taxonomy_display_category])
    .map(key => isTaxonomyPrimaryKey(key) ? key : 'unclassified'))]
    .sort((a, b) => TAXONOMY_PRIMARY_KEYS.indexOf(a) - TAXONOMY_PRIMARY_KEYS.indexOf(b));
  if (!primaryCategories.length) primaryCategories.push('unclassified');

  const rawActivities = row.taxonomy_leaf_activities;
  if (rawActivities !== undefined && (!Array.isArray(rawActivities) || rawActivities.length > 256)) throw new TypeError('Invalid taxonomy leaf activities.');
  const leafActivities = (rawActivities as unknown[] | undefined ?? []).map(item => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new TypeError('Invalid taxonomy leaf activity.');
    const activity = item as Record<string, unknown>;
    const key = safeText(activity.key, 'leaf key');
    const label = safeText(activity.label, 'leaf label');
    if (!key || !label) throw new TypeError('Invalid taxonomy leaf activity.');
    return { key, label };
  });

  const rawAssignments = row.taxonomy_assignments;
  if (rawAssignments !== undefined && (!Array.isArray(rawAssignments) || rawAssignments.length > 256)) throw new TypeError('Invalid taxonomy assignments.');
  const assignments: TaxonomyAssignment[] = (rawAssignments as unknown[] | undefined ?? []).map(item => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new TypeError('Invalid taxonomy assignment.');
    const assignment = item as Record<string, unknown>;
    const method = safeText(assignment.method, 'method');
    const status = safeText(assignment.status, 'status');
    const taxonomyVersion = safeText(assignment.taxonomy_version, 'version');
    if (!METHODS.includes(method ?? '') || !STATUSES.includes(status ?? '') || !taxonomyVersion) throw new TypeError('Invalid taxonomy assignment.');
    return {
      primaryKey: isTaxonomyPrimaryKey(assignment.primary_key) ? assignment.primary_key : 'unclassified',
      leafKey: safeText(assignment.leaf_key, 'leaf key'), leafLabel: safeText(assignment.leaf_label, 'leaf label'),
      sourceCodeReference: safeText(assignment.source_code_reference, 'source code reference'),
      sourceLabelReference: safeText(assignment.source_label_reference, 'source label reference'),
      sourceCode: safeText(assignment.source_code, 'source code'), sourceLabel: safeText(assignment.source_label, 'source label'),
      method: method as TaxonomyMethod, status: status as TaxonomyStatus, taxonomyVersion,
      crosswalkVersion: safeText(assignment.crosswalk_version, 'crosswalk version'),
      rulesetVersion: safeText(assignment.ruleset_version, 'ruleset version'),
      observationId: safeText(assignment.observation_id, 'observation reference'),
      sourceRecordId: safeText(assignment.source_record_id, 'source record reference'),
      artifactId: safeText(assignment.artifact_id, 'artifact reference'),
    };
  });
  const rawDisplay = row.taxonomy_display_category;
  const displayCategory = isTaxonomyPrimaryKey(rawDisplay) ? rawDisplay
    : rawDisplay !== undefined ? 'unclassified'
      : primaryCategories.length === 1 ? primaryCategories[0]! : 'unclassified';
  return {
    displayCategory,
    primaryCategories,
    leafActivities: [...new Map(leafActivities.map(activity => [activity.key, activity])).values()].sort((a, b) => a.key.localeCompare(b.key)),
    assignments,
    taxonomyVersion: assignments[0]?.taxonomyVersion ?? TAXONOMY_VERSION,
  };
}

export function taxonomySearchText(
  values: Readonly<{ leafActivities?: readonly TaxonomyLeafActivity[]; assignments?: readonly TaxonomyAssignment[] }> | null | undefined,
): string {
  if (!values) return '';
  return [
    ...(values.leafActivities ?? []).flatMap(activity => [activity.key, activity.label]),
    ...(values.assignments ?? []).flatMap(assignment => [assignment.leafKey, assignment.leafLabel, assignment.sourceCode, assignment.sourceLabel]),
  ].filter((value): value is string => Boolean(value)).join(' ');
}

/** Any selected category matches; source is ANDed as a separate filter dimension. */
export function taxonomyMatchesFilters<T extends Readonly<{
  taxonomy?: TaxonomyClassification | null;
  sourceId?: string | null;
  source?: string | null;
  category?: string | null;
}>>(
  record: T,
  selectedCategories: readonly TaxonomyPrimaryKey[],
  selectedSource: string | null,
): boolean {
  const categories = record.taxonomy?.primaryCategories ??
    (isTaxonomyPrimaryKey(record.category) ? [record.category] : ['unclassified']);
  const categoryMatches = selectedCategories.length === 0 || selectedCategories.some(key => categories.includes(key));
  const source = record.sourceId ?? record.source ?? null;
  return categoryMatches && (selectedSource === null || source === selectedSource);
}
