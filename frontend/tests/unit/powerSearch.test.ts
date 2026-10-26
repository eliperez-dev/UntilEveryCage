import { describe, expect, it } from 'vitest';
import { DEFAULT_LAB_STATE } from '../../src/design-lab/contract';
import { applySearchSuggestion, areaScopeFromBounds, parseSearch, publicSearchFilters, searchSuggestions } from '../../src/features/search/powerSearch';
import { encodeLabHash, reduceLabState } from '../../src/design-lab/state';

const facets = { countries: [{ value: 'ES', label: 'Spain', count: 4 }, { value: 'FR', label: 'France', count: 2 }], sources: [{ value: 'synthetic-register', label: 'Synthetic food register', count: 4 }], categories: [], activities: [] };

describe('structured map search', () => {
  it('only interprets exact country suffixes and recognized category phrases', () => {
    expect(parseSearch('poultry in Spain', DEFAULT_LAB_STATE.filters, facets)).toMatchObject({ query: 'poultry', filters: { countries: ['ES'] } });
    expect(parseSearch('poultry en España', DEFAULT_LAB_STATE.filters, facets)).toMatchObject({ query: 'poultry', filters: { countries: ['ES'] } });
    expect(parseSearch('slaughterhouses in Spain', DEFAULT_LAB_STATE.filters, facets)).toMatchObject({ query: '', filters: { countries: ['ES'], categories: ['slaughter'] } });
    expect(parseSearch('mataderos en España', DEFAULT_LAB_STATE.filters, facets, 'es')).toMatchObject({ query: '', filters: { countries: ['ES'], categories: ['slaughter'] } });
    expect(parseSearch('poultry in neverland', DEFAULT_LAB_STATE.filters, facets).query).toBe('poultry in neverland');
    expect(parseSearch('poultry in Portugal', DEFAULT_LAB_STATE.filters, facets).query).toBe('poultry in Portugal');
    expect(parseSearch('slaughterhouses near Spain', DEFAULT_LAB_STATE.filters, facets).query).toBe('slaughterhouses near Spain');
  });

  it('builds localized facet suggestions and applies them without losing other dimensions', () => {
    const country = searchSuggestions('poultry in Espa', facets, 'es').find(option => option.kind === 'country')!;
    expect(country).toEqual({ kind: 'country', value: 'ES', label: 'España', query: 'poultry' });
    const result = applySearchSuggestion(country, { ...DEFAULT_LAB_STATE.filters, categories: ['slaughter'], countries: ['FR'] });
    expect(result).toMatchObject({ query: 'poultry', filters: { countries: ['FR', 'ES'], categories: ['slaughter'] } });
    expect(searchSuggestions('food reg', facets)).toContainEqual({ kind: 'source', value: 'synthetic-register', label: 'Synthetic food register', query: '' });
    expect(searchSuggestions('slaughter', facets)[0]).toMatchObject({ kind: 'category', value: 'slaughter' });
    expect(searchSuggestions('x', facets)).toEqual([]);
  });

  it('shares every public list predicate with the map match request', () => {
    const state = { ...DEFAULT_LAB_STATE, query: ' poultry ', sourceId: 'synthetic-one', filters: { ...DEFAULT_LAB_STATE.filters, countries: ['ES', 'FR'], categories: ['slaughter', 'processing_and_preparation'], sources: ['synthetic-two'], precisions: ['city' as const] }, searchScope: { kind: 'radius' as const, label: 'Synthetic city', latitude: 40, longitude: -3, radiusKm: 25 } };
    expect(publicSearchFilters(state)).toEqual({ q: 'poultry', category_keys: ['slaughter', 'processing_and_preparation'], country_code: 'ES,FR', source_id: 'synthetic-one,synthetic-two', display_precision: 'city', latitude: 40, longitude: -3, radius_km: 25 });
    const area = publicSearchFilters({ ...state, searchScope: { kind: 'area', bounds: { west: -4, east: 4, south: 38, north: 44 } } });
    expect(area).toMatchObject({ min_lon: -4, max_lon: 4, min_lat: 38, max_lat: 44 });
    expect(area).not.toHaveProperty('radius_km');
  });

  it('normalizes full-world views but rejects crossing or degenerate bounds', () => {
    expect(areaScopeFromBounds({ west: -220, east: 200, south: -86, north: 86 })).toEqual({ kind: 'area', bounds: { west: -180, east: 180, south: -86, north: 86 } });
    expect(areaScopeFromBounds({ west: 370, east: 390, south: 20, north: 30 })).toEqual({ kind: 'area', bounds: { west: 10, east: 30, south: 20, north: 30 } });
    expect(areaScopeFromBounds({ west: 170, east: 190, south: 20, north: 30 })).toBeNull();
    expect(areaScopeFromBounds({ west: 1, east: 1, south: 20, north: 30 })).toBeNull();
    expect(areaScopeFromBounds({ west: NaN, east: 20, south: 20, north: 30 })).toBeNull();
  });

  it('applies a phrase atomically, returns to results, and keeps scope/query out of history', () => {
    const scope = { kind: 'radius' as const, label: 'Synthetic city', latitude: 40, longitude: -3, radiusKm: 25 };
    const initial = { ...DEFAULT_LAB_STATE, selectedId: 'synthetic-facility', searchScope: scope };
    const searched = reduceLabState(initial, { type: 'search', value: parseSearch('poultry in Spain', initial.filters, facets) });
    expect(searched).toMatchObject({ selectedId: null, listOpen: true, query: 'poultry', filters: { countries: ['ES'] }, searchScope: scope });
    expect(reduceLabState({ ...searched, selectedId: 'synthetic-facility' }, { type: 'results' })).toMatchObject({ selectedId: null, listOpen: true, query: 'poultry', searchScope: scope });
    expect(reduceLabState({ ...searched, selectedId: 'synthetic-facility', aggregateMemberIds: ['synthetic-facility'] }, { type: 'close-workspace' })).toMatchObject({ selectedId: null, listOpen: false, aggregateMemberIds: null, query: 'poultry', searchScope: scope });
    expect(encodeLabHash(searched)).not.toMatch(/poultry|Synthetic|radius|40|-3/);
    expect(reduceLabState(searched, { type: 'reset-filters' })).toMatchObject({ query: '', searchScope: null, filters: DEFAULT_LAB_STATE.filters });
  });
});
