import { DEFAULT_LAB_STATE, DIRECTIONS, SCENARIOS, type LabAction, type LabFilters, type LabState } from './contract';

const safeNumber = (value: string | null, fallback: number, min: number, max: number) => {
  if (value === null || value.trim() === '') return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : fallback;
};
const unique = <T extends string>(values: readonly T[]) => [...new Set(values)];
export function decodeLabHash(hash: string): LabState {
  const queryString = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '';
  const q = new URLSearchParams(queryString);
  const direction = DIRECTIONS.find(value => value === q.get('f1a')) ?? DEFAULT_LAB_STATE.direction;
  const scenario = SCENARIOS.find(value => value === q.get('scenario')) ?? DEFAULT_LAB_STATE.scenario;
  const precisionOptions = ['exact', 'city', 'coarse', 'unmapped'] as const;
  const filters: LabFilters = {
    categories: unique(q.getAll('category').filter(value => ['Poultry', 'Pig', 'Dairy', 'Processing', 'Laboratory', 'Aquaculture'].includes(value))),
    precisions: unique(q.getAll('precision').filter((value): value is (typeof precisionOptions)[number] => precisionOptions.some(option => option === value))),
  };
  return { ...DEFAULT_LAB_STATE, direction, scenario, query: q.get('q') ?? '', selectedId: q.get('selected'), filters,
    basemap: q.get('basemap') === 'satellite' ? 'satellite' : 'vector', listOpen: q.get('list') !== 'closed',
    viewport: { centerLat: safeNumber(q.get('lat'), 45, -90, 90), centerLon: safeNumber(q.get('lon'), 5, -180, 180), zoom: safeNumber(q.get('z'), 2, 1, 18) } };
}
export function encodeLabHash(state: LabState): string {
  const q = new URLSearchParams({ f1a: state.direction, scenario: state.scenario });
  if (state.query) q.set('q', state.query); if (state.selectedId) q.set('selected', state.selectedId);
  if (state.basemap !== 'vector') q.set('basemap', state.basemap); if (!state.listOpen) q.set('list', 'closed');
  if (state.viewport.centerLat !== 45) q.set('lat', String(state.viewport.centerLat));
  if (state.viewport.centerLon !== 5) q.set('lon', String(state.viewport.centerLon));
  if (state.viewport.zoom !== 2) q.set('z', String(state.viewport.zoom));
  for (const category of state.filters.categories) q.append('category', category);
  for (const precision of state.filters.precisions) q.append('precision', precision);
  return `#/map?${q.toString()}`;
}
export function reduceLabState(state: LabState, action: LabAction): LabState {
  switch (action.type) {
    case 'direction': return { ...state, direction: action.value };
    case 'scenario': return { ...state, scenario: action.value };
    case 'query': return { ...state, query: action.value, selectedId: null };
    case 'select': return { ...state, selectedId: action.value };
    case 'cluster': return { ...state, expandedCluster: action.value };
    case 'basemap': return { ...state, basemap: action.value };
    case 'list': return { ...state, listOpen: action.value };
    case 'viewport': return { ...state, viewport: action.value };
    case 'filters': return { ...state, filters: { categories: unique(action.value.categories), precisions: unique(action.value.precisions) } };
    case 'reset-filters': return { ...state, query: '', filters: DEFAULT_LAB_STATE.filters, selectedId: null };
  }
}
