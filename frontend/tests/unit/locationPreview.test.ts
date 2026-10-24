import { describe, expect, it } from 'vitest';
import { locationPreviewMode, locationPreviewZoom } from '../../src/features/locations/locationPreview';

describe('location preview presentation', () => {
  it('uses satellite for source-provided points and roads for approximate points', () => {
    expect(locationPreviewMode('exact')).toBe('satellite');
    expect(locationPreviewMode('source_reported')).toBe('satellite');
    expect(locationPreviewMode('city')).toBe('roads');
    expect(locationPreviewMode('coarse')).toBe('roads');
    expect(locationPreviewMode('unmapped')).toBe('roads');
    expect(locationPreviewZoom('exact')).toBeGreaterThan(locationPreviewZoom('city'));
  });
});
