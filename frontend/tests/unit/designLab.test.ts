import { describe, expect, it } from 'vitest';
import { labRecords } from '../../src/design-lab/fixtures';
import { decodeLabHash, encodeLabHash, reduceLabState } from '../../src/design-lab/state';
import { createLabViewModel } from '../../src/design-lab/viewModel';

describe('F1A shared design lab', () => {
  it('provides a frozen deterministic 96-record corpus across every precision and category', () => {
    expect(labRecords).toHaveLength(96);
    expect(new Set(labRecords.map(record => record.precision))).toEqual(new Set(['exact', 'city', 'coarse', 'unmapped']));
    expect(new Set(labRecords.map(record => record.category)).size).toBe(6);
    expect(labRecords.filter(record => record.precision === 'unmapped').every(record => record.latitude === null && record.longitude === null)).toBe(true);
  });

  it('round trips search, selection, filters, viewport, list, direction, scenario, and basemap state', () => {
    const state = decodeLabHash('#/map?f1a=field&scenario=dense&q=pig&selected=syn-042&cluster=aarhus&basemap=satellite&list=closed&lat=40&lon=-12&z=5&category=Pig&category=Dairy&precision=city');
    expect(decodeLabHash(encodeLabHash(state))).toEqual(state);
  });

  it('preserves every review state when switching directions', () => {
    const state = decodeLabHash('#/map?f1a=atlas&scenario=dense&q=pig&selected=syn-042&cluster=aarhus&lat=40&lon=-12&z=5&category=Pig&precision=coarse');
    expect(reduceLabState(state, { type: 'direction', value: 'index' })).toMatchObject({
      direction: 'index', scenario: 'dense', query: 'pig', selectedId: 'syn-042',
      expandedCluster: 'aarhus',
      viewport: { centerLat: 40, centerLon: -12, zoom: 5 }, filters: { categories: ['Pig'], precisions: ['coarse'] },
    });
  });

  it('clamps unsafe viewport values and ignores invalid review parameters', () => {
    expect(decodeLabHash('#/map?f1a=unknown&scenario=unknown&lat=999&lon=-999&z=not-a-number&precision=fictional')).toMatchObject({
      direction: 'atlas', scenario: 'default', viewport: { centerLat: 90, centerLon: -180, zoom: 2 }, filters: { precisions: [] },
    });
  });

  it('keeps global search results separate from map placement and preserves unmapped rows', () => {
    const model = createLabViewModel(labRecords, decodeLabHash('#/map?q=synthetic'));
    expect(model.listRecords).toHaveLength(96);
    expect(model.unmappedCount).toBeGreaterThan(0);
    expect(model.mapRecords.every(record => record.precision !== 'unmapped' && record.latitude !== null && record.longitude !== null)).toBe(true);
    expect(model.listRecords.some(record => record.precision === 'unmapped')).toBe(true);
  });

  it('applies OR within category and precision groups, then AND across groups and search', () => {
    const state = reduceLabState(decodeLabHash('#/map?q=synthetic'), { type: 'filters', value: { categories: ['Poultry', 'Pig'], precisions: ['exact'] } });
    const model = createLabViewModel(labRecords, state);
    expect(model.listRecords.length).toBeGreaterThan(0);
    expect(model.listRecords.every(record => ['Poultry', 'Pig'].includes(record.category) && record.precision === 'exact')).toBe(true);
  });

  it('represents loading, empty, error, and mobile scenarios without changing the corpus source', () => {
    const modelFor = (scenario: string) => createLabViewModel(labRecords, decodeLabHash(`#/map?scenario=${scenario}`));
    expect(modelFor('loading').isLoading).toBe(true);
    expect(modelFor('empty').isEmpty).toBe(true);
    expect(modelFor('error').hasError).toBe(true);
    expect(modelFor('mobile').listRecords).toHaveLength(96);
  });
});
