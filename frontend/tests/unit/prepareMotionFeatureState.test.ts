import { describe, expect, it, vi } from 'vitest';
import { prepareMotionFeatureState } from '../../src/map/prepareMotionFeatureState';

describe('prepaint feature-state preparation', () => {
  it('updates only location attributes without repainting the map or advancing camera tasks', () => {
    const context = {}, prepare = vi.fn(), base = vi.fn();
    const map = {
      style: { tileManagers: { locations: { prepare }, base: { prepare: base } } },
      redraw: vi.fn(), _render: vi.fn(), _renderTaskQueue: { run: vi.fn() },
      painter: { context, render: vi.fn() },
    };
    prepareMotionFeatureState(map as any);
    expect(prepare).toHaveBeenCalledOnce(); expect(prepare).toHaveBeenCalledWith(context);
    expect(base).not.toHaveBeenCalled(); expect(map.painter.render).not.toHaveBeenCalled();
    expect(map.redraw).not.toHaveBeenCalled(); expect(map._render).not.toHaveBeenCalled(); expect(map._renderTaskQueue.run).not.toHaveBeenCalled();
  });
  it('does not start a renderer before the native source exists', () => {
    const map = { redraw: vi.fn() };
    prepareMotionFeatureState(map as any); expect(map.redraw).not.toHaveBeenCalled();
  });
  it('does not prepare a removed renderer', () => {
    const prepare = vi.fn(), map = { style: { tileManagers: { locations: { prepare } } }, redraw: vi.fn() };
    prepareMotionFeatureState(map as any);
    expect(prepare).not.toHaveBeenCalled(); expect(map.redraw).not.toHaveBeenCalled();
  });
});
