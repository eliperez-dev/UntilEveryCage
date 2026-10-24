import type { CategoryPresentationKey } from './categoryPresentation';

export type LocationPreviewMode = 'satellite' | 'roads';

export function locationPreviewMode(precision: string | null | undefined): LocationPreviewMode {
  return precision === 'exact' || precision === 'source_reported' || precision === 'source_provided_unverified'
    ? 'satellite'
    : 'roads';
}

export function locationPreviewZoom(precision: string | null | undefined): number {
  return locationPreviewMode(precision) === 'satellite' ? 13 : 8;
}

const pinByCategory: Readonly<Record<CategoryPresentationKey, string>> = {
  animal_keeping_and_production: 'green',
  slaughter: 'red',
  processing_and_preparation: 'grey',
  research_and_animal_use: 'violet',
  other_regulated_premises: 'orange',
  unclassified: 'grey',
};

export function locationPreviewPinFile(
  category: string | null | undefined,
  sourceCategoryMap: Readonly<Record<string, CategoryPresentationKey>>,
): string {
  const key = category ? sourceCategoryMap[category] ?? 'unclassified' : 'unclassified';
  return `marker-icon-2x-${pinByCategory[key]}.png`;
}
