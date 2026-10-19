import { describe, expect, it } from 'vitest';
import { DEFAULT_LAB_STATE } from '../../src/design-lab/contract';
import { decodeLabHash, encodeLabHash, reduceLabState } from '../../src/design-lab/state';

describe('design-lab state repairs', () => {
  it('decodes a retired muted basemap link as Street and never re-emits it', () => {
    const state = decodeLabHash('#/map?basemap=muted&lat=51&lon=-1&z=8');

    expect(state.basemap).toBe('vector');
    expect(encodeLabHash(state)).not.toContain('basemap=');
    expect(encodeLabHash({ ...state, basemap: 'satellite' })).toContain('basemap=satellite');
  });

  it('clears every search criterion, selection, and aggregate while retaining the map context', () => {
    const populated = {
      ...DEFAULT_LAB_STATE,
      query: 'packing plant',
      sourceId: 'source-17',
      selectedId: 'facility-12',
      aggregateMemberIds: ['facility-12', 'facility-13'],
      basemap: 'satellite' as const,
      listOpen: true,
      viewport: { centerLat: 48.8566, centerLon: 2.3522, zoom: 9 },
      filters: { categories: ['processing'], precisions: ['city' as const], countries: ['FR'], sources: ['source-17'], activities: ['slaughter'] },
    };

    const cleared = reduceLabState(populated, { type: 'reset-filters' });

    expect(cleared).toMatchObject({
      query: '', sourceId: null, selectedId: null, aggregateMemberIds: null,
      filters: { categories: [], precisions: [], countries: [], sources: [], activities: [] },
    });
    expect(cleared.viewport).toEqual(populated.viewport);
    expect(cleared.basemap).toBe('satellite');
    expect(cleared.listOpen).toBe(true);
  });
});
