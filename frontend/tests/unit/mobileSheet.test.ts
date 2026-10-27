import { describe, expect, it } from 'vitest';
import { filterViewportHeight, nearestSheetSnap, sheetHeights, sheetKeyboardSnap } from '../../src/design-lab/components/mobileSheet';
describe('mobile search sheet geometry', () => {
  it('bounds the filter scroll viewport below its actual toolbar position', () => {
    expect(filterViewportHeight(641,844)).toBe(195);
    expect(filterViewportHeight(541,667,20)).toBe(98);
    expect(filterViewportHeight(800,667)).toBe(0);
  });
  it('uses the actual remaining workspace and safe area', () => {
    expect(sheetHeights(700)).toEqual({ collapsed: 56, middle: 336, expanded: 630 });
    expect(sheetHeights(700, {}, 20).collapsed).toBe(76);
    expect(sheetHeights(40)).toEqual({ collapsed: 40, middle: 40, expanded: 40 });
    expect(sheetHeights(0)).toEqual({ collapsed: 0, middle: 0, expanded: 0 });
  });
  it('bounds temporary debug settings and snaps without overshoot', () => {
    const heights = sheetHeights(600, { middlePercent: 900, expandedPercent: -2 });
    expect(heights).toEqual({ collapsed: 56, middle: 390, expanded: 450 });
    expect(nearestSheetSnap(-100, heights)).toBe('collapsed');
    expect(nearestSheetSnap(400, heights)).toBe('middle');
    expect(nearestSheetSnap(1200, heights)).toBe('expanded');
  });
  it('offers bounded directional keyboard steps and direct endpoints', () => {
    expect(sheetKeyboardSnap('ArrowUp', 'collapsed')).toBe('middle');
    expect(sheetKeyboardSnap('ArrowUp', 'expanded')).toBe('expanded');
    expect(sheetKeyboardSnap('ArrowDown', 'expanded')).toBe('middle');
    expect(sheetKeyboardSnap('ArrowDown', 'collapsed')).toBe('collapsed');
    expect(sheetKeyboardSnap('Home', 'expanded')).toBe('collapsed');
    expect(sheetKeyboardSnap('End', 'collapsed')).toBe('expanded');
    expect(sheetKeyboardSnap('Tab', 'middle')).toBeNull();
  });
});
