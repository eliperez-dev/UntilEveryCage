import { describe, expect, it, vi } from 'vitest';
import { syncSelectionOverlayWhenReady } from '../../src/design-lab/components/selectionOverlay';

describe('selection updates while unrelated tiles are pending', () => {
  it('applies a first selection and its dismissal even when overall style readiness is false', () => {
    let selected: string | null = 'synthetic-first-click';
    let displayed: string | null = null;
    const map = { getSource: () => ({}), getLayer: () => ({}), isStyleLoaded: vi.fn(() => false) };
    const sync = () => { displayed = selected; };
    syncSelectionOverlayWhenReady(map, sync);
    expect(displayed).toBe('synthetic-first-click');
    selected = null;
    syncSelectionOverlayWhenReady(map, sync);
    expect(displayed).toBeNull();
    expect(map.isStyleLoaded).not.toHaveBeenCalled();
  });

  it('waits for actual overlay reconstruction rather than writing into a missing source or layer', () => {
    const sync = vi.fn();
    syncSelectionOverlayWhenReady(undefined, sync);
    syncSelectionOverlayWhenReady({ getSource: () => undefined, getLayer: () => ({}) }, sync);
    syncSelectionOverlayWhenReady({ getSource: () => ({}), getLayer: () => undefined }, sync);
    expect(sync).not.toHaveBeenCalled();
    syncSelectionOverlayWhenReady({ getSource: () => ({}), getLayer: () => ({}) }, sync);
    expect(sync).toHaveBeenCalledOnce();
  });
});
