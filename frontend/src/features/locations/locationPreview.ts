export type LocationPreviewMode = 'satellite' | 'roads';

export function locationPreviewMode(precision: string | null | undefined): LocationPreviewMode {
  return precision === 'exact' || precision === 'source_reported' || precision === 'source_provided_unverified'
    ? 'satellite'
    : 'roads';
}

export function locationPreviewZoom(precision: string | null | undefined): number {
  return locationPreviewMode(precision) === 'satellite' ? 13 : 8;
}
