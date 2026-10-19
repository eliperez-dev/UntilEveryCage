import { describe, expect, it } from 'vitest';
import { publicReleaseLabel } from '../../src/features/locations/releasePresentation';

describe('public release presentation', () => {
  it('uses trusted date labels and never exposes release identifiers', () => {
    expect(publicReleaseLabel('release-2026-10-18', '2026-10-18')).toBe('2026-10-18');
    expect(publicReleaseLabel('release-2026-10-18')).toBe('2026-10-18');
    expect(publicReleaseLabel('opaque-current')).toBe('Public release');
  });

  it('retains the approved legacy v0 human label', () => {
    expect(publicReleaseLabel('v0-candidate-2026-10-04-r3')).toBe('v0: Early Access');
  });
});
