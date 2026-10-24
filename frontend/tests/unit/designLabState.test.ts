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

  it('round trips canonical V2 category filters without dropping them on hash changes', () => {
    const selected = reduceLabState(DEFAULT_LAB_STATE, {
      type: 'filters',
      value: { ...DEFAULT_LAB_STATE.filters, categories: ['slaughter', 'processing_and_preparation'] },
    });

    const restored = decodeLabHash(encodeLabHash(selected));

    expect(restored.filters.categories).toEqual(['slaughter', 'processing_and_preparation']);
  });

  it('keeps legacy public map links readable while omitting private fixture state from public URLs', () => {
    const legacy = decodeLabHash('#/map?scenario=dense&f1a=field&category=slaughter');
    expect(legacy.scenario).toBe('dense');
    const publicHash = encodeLabHash(legacy, false, true);
    expect(publicHash).not.toContain('scenario=');
    expect(publicHash).not.toContain('f1a=');
    expect(publicHash).toContain('category=slaughter');
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
