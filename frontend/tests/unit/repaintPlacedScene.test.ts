import { describe, expect, it, vi } from 'vitest';
import { repaintPlacedScene } from '../../src/map/repaintPlacedScene';

describe('placed-scene feature-state repaint', () => {
  it('reuses current placement and options without advancing camera tasks or tile managers', () => {
    const order: string[] = [], style = {}, options = { zooming: true, rotating: false };
    const map = {
      style, redraw: vi.fn(), _render: vi.fn(), _renderTaskQueue: { run: vi.fn() },
      painter: { options, context: { setDirty: () => order.push('dirty') }, setBaseState: () => order.push('base'), render: vi.fn(() => order.push('paint')) },
    };
    repaintPlacedScene(map as any);
    expect(order).toEqual(['dirty', 'base', 'paint']);
    expect(map.painter.render).toHaveBeenCalledWith(style, options);
    expect(map.redraw).not.toHaveBeenCalled(); expect(map._render).not.toHaveBeenCalled(); expect(map._renderTaskQueue.run).not.toHaveBeenCalled();
  });
  it('uses the public renderer before a native placed scene is available', () => {
    const map = { redraw: vi.fn() };
    repaintPlacedScene(map as any); expect(map.redraw).toHaveBeenCalledOnce();
  });
});
