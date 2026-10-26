import { describe, expect, it } from 'vitest';
import { DEFAULT_LAB_STATE } from '../../src/design-lab/contract';
import { decodeLabHash, encodeLabHash, encodeMapNavigationHash, reduceLabState } from '../../src/design-lab/state';

describe('design-lab state repairs', () => {
  it('keeps device-derived camera movement out of public links through later actions', () => {
    const start = decodeLabHash('#/map?lat=38&lon=-96&z=4');
    const device = reduceLabState(start, { type: 'private-camera', value: { centerLat: 12.345678, centerLon: 98.765432, zoom: 12 } });
    const panned = reduceLabState(device, { type: 'viewport', value: { centerLat: 12.35, centerLon: 98.77, zoom: 13 } });
    const searched = reduceLabState(panned, { type: 'query', value: 'synthetic query' });
    const selected = reduceLabState(searched, { type: 'select', value: 'synthetic-facility' });
    const closed = reduceLabState(selected, { type: 'close-workspace' });
    expect(closed.viewport).toEqual(panned.viewport);
    expect(decodeLabHash(encodeLabHash(closed, false, true)).viewport).toEqual(start.viewport);
    expect(encodeLabHash(selected, false, true)).toContain('selected=synthetic-facility');
    expect(encodeLabHash(closed, false, true)).not.toMatch(/12\.35|98\.77|synthetic.query|navigationViewport/);
    const again = reduceLabState(device, { type: 'private-camera', value: { centerLat: 3, centerLon: 4, zoom: 10 } });
    expect(again.navigationViewport).toEqual(start.viewport);
  });

  it('rejects invalid device camera values without changing the navigation camera', () => {
    for (const viewport of [{ centerLat: NaN, centerLon: 0, zoom: 12 }, { centerLat: 91, centerLon: 0, zoom: 12 }, { centerLat: 0, centerLon: 181, zoom: 12 }, { centerLat: 0, centerLon: 0, zoom: 20 }]) {
      expect(reduceLabState(DEFAULT_LAB_STATE, { type: 'private-camera', value: viewport })).toBe(DEFAULT_LAB_STATE);
    }
  });
  it('decodes a retired muted basemap link as Street and never re-emits it', () => {
    const state = decodeLabHash('#/map?basemap=muted&lat=51&lon=-1&z=8');

    expect(state.basemap).toBe('vector');
    expect(encodeLabHash(state)).not.toContain('basemap=');
    expect(encodeLabHash({ ...state, basemap: 'satellite' })).toContain('basemap=satellite');
  });

  it('round trips non-default camera pitch and bearing while keeping flat URLs compact', () => {
    const tilted = decodeLabHash('#/map?lat=38&lon=-96&z=4&pitch=45&bearing=27');
    expect(tilted.viewport).toMatchObject({ centerLat: 38, centerLon: -96, zoom: 4, pitch: 45, bearing: 27 });
    expect(decodeLabHash(encodeLabHash(tilted)).viewport).toMatchObject(tilted.viewport);
    expect(encodeLabHash(DEFAULT_LAB_STATE)).not.toMatch(/pitch=|bearing=/);
    expect(decodeLabHash('#/map?pitch=200&bearing=oops').viewport).toMatchObject({ pitch: 85, bearing: 0 });
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

  it('keeps public masthead and nested map links free of fixture scenarios', () => {
    const databaseHref = '#/database?release_id=release-2026-10-18&lat=38&lon=-96&z=4&list=closed&scenario=default&f1a=field';
    const publicMapLink = encodeMapNavigationHash(databaseHref);
    expect(publicMapLink).toContain('release_id=release-2026-10-18');
    expect(publicMapLink).toContain('lat=38');
    expect(publicMapLink).not.toContain('scenario=');
    expect(publicMapLink).not.toContain('f1a=');
    expect(encodeMapNavigationHash('#/database?lat=38', 'dense')).toContain('scenario=dense');
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
