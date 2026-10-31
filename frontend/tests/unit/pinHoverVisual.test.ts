import { describe, expect, it } from 'vitest';
import { pinHoverVisual } from '../../src/design-lab/pinHoverVisual';

describe('pin hover highlight geometry', () => {
  it('uses the actual PNG alpha mask at its bottom-anchored rendered size', () => {
    expect(pinHoverVisual(true, 0.8, 6.5, '/v2-preview/')).toMatchObject({ kind: 'pin', width: 20,
      transform: 'translate(-50%, -100%)', maskUrl: '/v2-preview/v1-pins/marker-icon-2x-grey.png' });
    expect(pinHoverVisual(true, 0.8, 6.5).height).toBeCloseTo(32.8);
    expect(pinHoverVisual(true, 1.6, 6.5).height).toBeCloseTo(65.6);
    expect(pinHoverVisual(true, 0.2, 6.5).width).toBe(15);
    expect(pinHoverVisual(true, NaN, 6.5).width).toBe(20);
  });
  it('uses a centered circular highlight for optimized dots, without a pin asset', () => {
    expect(pinHoverVisual(false, 0.8, 6.5)).toEqual({ kind: 'dot', width: 21, height: 21,
      transform: 'translate(-50%, -50%)', maskUrl: null });
    expect(pinHoverVisual(false, 1, 12).width).toBe(32);
    expect(pinHoverVisual(false, 1, NaN).width).toBe(21);
  });
  it('never embeds remote URLs or arbitrary CSS in a mask URL', () => {
    for (const value of ['https://example.test/', '//example.test/', '/bad");background:red;/*', 'javascript:alert(1)', '/path with spaces/']) {
      expect(pinHoverVisual(true, 0.8, 6.5, value).maskUrl).toBe('/v1-pins/marker-icon-2x-grey.png');
    }
  });
});
