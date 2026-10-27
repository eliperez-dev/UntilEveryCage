import { describe, expect, it } from 'vitest';
import { locationPreviewMode, locationPreviewZoom } from '../../src/features/locations/locationPreview';
import { locationPreviewPinFile } from '../../src/features/locations/locationPreview';
import { CATEGORY_PRIMARY_BY_SOURCE_KEY } from '../../src/features/locations/categoryPresentation';

describe('location preview presentation', () => {
  it('uses satellite for source-provided points and roads for approximate points', () => {
    expect(locationPreviewMode('exact')).toBe('satellite');
    expect(locationPreviewMode('source_reported')).toBe('satellite');
    expect(locationPreviewMode('city')).toBe('roads');
    expect(locationPreviewMode('coarse')).toBe('roads');
    expect(locationPreviewMode('unmapped')).toBe('roads');
    expect(locationPreviewZoom('exact')).toBe(15);
    expect(locationPreviewZoom('source_reported')).toBe(15);
    expect(locationPreviewZoom('city')).toBe(9);
    expect(locationPreviewZoom('coarse')).toBe(9);
  });

  it('uses the canonical V1 pin family and a neutral pin for unknown categories', () => {
    expect(locationPreviewPinFile('slaughter', CATEGORY_PRIMARY_BY_SOURCE_KEY)).toBe('marker-icon-2x-red.png');
    expect(locationPreviewPinFile('processing_and_preparation', CATEGORY_PRIMARY_BY_SOURCE_KEY)).toBe('marker-icon-2x-blue.png');
    expect(locationPreviewPinFile('unknown_source_activity', CATEGORY_PRIMARY_BY_SOURCE_KEY)).toBe('marker-icon-2x-grey.png');
  });
});
