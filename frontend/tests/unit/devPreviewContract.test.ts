import { describe, expect, it } from 'vitest';
import { canOpenDevPreview, DEV_PREVIEW_LABEL, DEV_PREVIEW_PATH, DEV_PREVIEW_QUERY, DEV_PREVIEW_TOKEN_HEADER } from '../../src/features/devPreview/devPreviewContract';

describe('dev preview boundary', () => {
  it('requires both a development build and the explicit mode', () => {
    expect(canOpenDevPreview(true, DEV_PREVIEW_QUERY)).toBe(true);
    expect(canOpenDevPreview(false, DEV_PREVIEW_QUERY)).toBe(false);
    expect(canOpenDevPreview(true, null)).toBe(false);
    expect(canOpenDevPreview(true, 'local-v2')).toBe(false);
  });

  it('keeps the route and label distinct from public V2', () => {
    expect(DEV_PREVIEW_PATH).toBe('/api/dev/preview/candidates');
    expect(DEV_PREVIEW_PATH).not.toContain('/api/v2/');
    expect(DEV_PREVIEW_TOKEN_HEADER).toBe('X-UEC-Dev-Preview-Token');
    expect(DEV_PREVIEW_LABEL).toContain('NOT REVIEWED OR PUBLISHED');
  });
});
