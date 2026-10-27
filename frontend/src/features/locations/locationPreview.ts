import { CATEGORY_PIN_COLORS, type CategoryPresentationKey } from './categoryPresentation';

export type LocationPreviewMode = 'satellite' | 'roads';

export function locationPreviewMode(precision: string | null | undefined): LocationPreviewMode {
  return precision === 'exact' || precision === 'source_reported' || precision === 'source_provided_unverified'
    ? 'satellite'
    : 'roads';
}

export function locationPreviewZoom(precision: string | null | undefined): number {
  return locationPreviewMode(precision) === 'satellite' ? 15 : 9;
}

export function locationPreviewPinFile(
  category: string | null | undefined,
  sourceCategoryMap: Readonly<Record<string, CategoryPresentationKey>>,
): string {
  const key = category ? sourceCategoryMap[category] ?? 'unclassified' : 'unclassified';
  return `marker-icon-2x-${CATEGORY_PIN_COLORS[key]}.png`;
}
