import type { LocationSourceFacts } from '../../domain/location';
import type { TaxonomyClassification } from '../../domain/taxonomy';
import { CATEGORY_PRIMARY_BY_SOURCE_KEY, categoryPresentation, type CategoryPresentationKey } from './categoryPresentation';
import { locationPreviewPinFile } from './locationPreview';

export type ClassificationRecord = Readonly<{
  category?: string | null;
  sourceId?: string | null;
  taxonomy?: TaxonomyClassification | null;
  sourceFacts?: LocationSourceFacts | undefined;
  activitySource?: string | null;
}>;
type Translate = (label: string) => string;
const priority: readonly CategoryPresentationKey[] = ['slaughter', 'research_and_animal_use', 'processing_and_preparation', 'animal_keeping_and_production', 'other_regulated_premises', 'unclassified'];

/** Matches the complete-key priority used by the map's V1 pin expression. */
export function recordCategoryKey(record: ClassificationRecord): CategoryPresentationKey {
  const keys = record.taxonomy?.primaryCategories;
  return (keys?.length ? priority.find(key => keys.includes(key)) : undefined)
    ?? CATEGORY_PRIMARY_BY_SOURCE_KEY[record.category ?? ''] ?? 'unclassified';
}

export function recordCategoryIdentity(record: ClassificationRecord) {
  const key = recordCategoryKey(record);
  return { key, label: categoryPresentation(key).label, pinFile: locationPreviewPinFile(key, CATEGORY_PRIMARY_BY_SOURCE_KEY) };
}

export function classificationLabel(raw: string): string {
  return raw.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
    .replace(/\b(nrte|rte)\b/gi, acronym => acronym.toUpperCase())
    .replace(/^./, letter => letter.toLocaleUpperCase());
}
const identity = (label: string) => classificationLabel(label).toLocaleLowerCase();
const unique = (labels: readonly string[]) => [...new Map(labels.filter(Boolean).map(label => [identity(label), label])).values()];
function boundedSummary(text: string): string {
  if (text.length <= 220) return text;
  const excerpt = text.slice(0, 218);
  const boundary = excerpt.lastIndexOf(' ');
  return `${boundary > 140 ? excerpt.slice(0, boundary) : excerpt}…`;
}
function completeSourceTerm(label: string, term: string): boolean {
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(?:^|[^\\p{L}\\p{N}_-])${escaped}(?=$|[^\\p{L}\\p{N}_-])`, 'iu').test(label);
}

/** Source flags can contain explicit negative strings as well as boolean false. */
export function affirmativeSourceEntries(flags: Readonly<Record<string, string | boolean>> | undefined): Array<[string, string | boolean]> {
  return flags ? Object.entries(flags).filter(([, value]) => value === true || (typeof value === 'string' && Boolean(value.trim()) && !/^(?:no|n|false|0)$/i.test(value.trim()))).sort(([left], [right]) => left.localeCompare(right)) : [];
}

export function classificationSummary(record: ClassificationRecord, translate: Translate = label => label) {
  const generated = (label: string) => translate(classificationLabel(label));
  // Original source labels/codes remain intact here; generated activity labels
  // below are humanized separately. Neither display path changes stored values.
  const allSourceLabels = [...new Set([
    record.sourceFacts?.nativeActivityLabel, record.sourceFacts?.nativeActivityCode, record.activitySource,
    ...(record.taxonomy?.assignments.flatMap(item => [item.sourceLabel, item.sourceCode]) ?? []),
  ].filter((label): label is string => Boolean(label?.trim())).flatMap(label => label.split(';').map(term => term.trim()).filter(Boolean)))];
  const sourceLabels = allSourceLabels.filter(label => !allSourceLabels.some(other => other.length > label.length && completeSourceTerm(other, label)));
  const aphisTerms = [record.sourceFacts?.nativeActivityLabel, record.sourceFacts?.nativeActivityCode, record.activitySource,
    ...(record.taxonomy?.assignments.flatMap(item => [item.sourceLabel, item.sourceCode]) ?? [])].filter((label): label is string => Boolean(label));
  const aphisClasses = record.sourceId === 'us.aphis'
    ? unique(aphisTerms.flatMap(label => [...label.matchAll(/\bClass\s+([ABCFGHRTV])\b/gi)].map(match => match[1]!.toUpperCase()))) : [];
  const classLabels: Readonly<Record<string, string>> = {
    A: 'Breeder', B: 'Dealer', C: 'Exhibitor', F: 'Federal research facility', G: 'Agricultural research facility',
    H: 'Intermediate handler', R: 'Research facility', T: 'Carrier', V: 'VA hospital',
  };
  const registration = aphisClasses.map(code => `${translate(classLabels[code]!)} (${translate('Class')} ${code})`).join(', ');
  const aphisHeading = aphisClasses.length && aphisClasses.every(code => ['H', 'T', 'R'].includes(code)) ? 'APHIS registration' : 'APHIS classification';
  const aphisFallback = aphisClasses.some(code => ['B', 'C', 'H', 'T'].includes(code));
  const rawActivities = unique([
    ...(record.taxonomy?.leafActivities.map(item => classificationLabel(item.label)) ?? []),
    ...(!record.taxonomy && record.category && !priority.includes(record.category as CategoryPresentationKey) ? [classificationLabel(record.category)] : []),
    ...affirmativeSourceEntries(record.sourceFacts?.processingActivities).map(([key, value]) => `${classificationLabel(key)}${typeof value === 'string' && !/^(?:yes|y|true|1)$/i.test(value.trim()) ? `: ${classificationLabel(value)}` : ''}`),
  ]);
  const categories = unique((record.taxonomy?.primaryCategories?.length ? record.taxonomy.primaryCategories : [recordCategoryKey(record)]).map(key => categoryPresentation(key).label));
  const hasSpecificProcessing = record.taxonomy?.primaryCategories.includes('processing_and_preparation')
    && rawActivities.some(label => identity(label) !== 'processing' && !categories.some(category => identity(category) === identity(label)));
  const usefulActivities = rawActivities.filter(label => !categories.some(category => identity(category) === identity(label))
    && !(aphisFallback && identity(label) === 'general food business')
    && !(hasSpecificProcessing && identity(label) === 'processing'));
  const activities = usefulActivities.map(generated);
  const summaryItems = activities.length ? activities.slice(0, 3) : [];
  const summary = registration ? `${translate(aphisHeading)}: ${registration}.`
    : summaryItems.length ? `${translate('Recorded activities')}: ${summaryItems.join(', ')}${activities.length > 3 ? ', …' : '.'}`
      : '';
  return { summary: boundedSummary(summary), categories: categories.map(translate), activities, sourceLabels, supportingActivities: rawActivities.map(generated), hasAphisClassification: Boolean(registration) };
}
