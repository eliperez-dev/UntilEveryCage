import { DEFAULT_LAB_STATE, DIRECTIONS, SCENARIOS, type LabAction, type LabFilters, type LabState } from './contract';
import { TAXONOMY_PRIMARY_KEYS } from '../domain/taxonomy';
import { isSearchScope } from '../features/search/powerSearch';
import { DEFAULT_NEARBY_RADIUS_KM, nearbyOverviewZoom, validDeviceLocation } from '../features/search/nearbySearch';

const safeNumber = (value: string | null, fallback: number, min: number, max: number) => {
  if (value === null || value.trim() === '') return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : fallback;
};
const unique = <T extends string>(values: readonly T[]) => [...new Set(values)];
const categoryOptions = new Set<string>([
  ...TAXONOMY_PRIMARY_KEYS,
  // Synthetic fixtures still use the original presentation labels.
  'Poultry', 'Pig', 'Dairy', 'Processing', 'Laboratory', 'Aquaculture',
]);
export function decodeLabHash(hash: string): LabState {
  const queryString = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '';
  const q = new URLSearchParams(queryString);
  const direction = 'field';
  const scenario = SCENARIOS.find(value => value === q.get('scenario')) ?? DEFAULT_LAB_STATE.scenario;
  const precisionOptions = ['exact', 'source_reported', 'approximate', 'city', 'coarse', 'unmapped'] as const;
  const filters: LabFilters = {
    categories: unique(q.getAll('category').filter(value => categoryOptions.has(value))),
    precisions: unique(q.getAll('precision').filter((value): value is (typeof precisionOptions)[number] => precisionOptions.some(option => option === value))),
    countries: unique(q.getAll('country').filter(value => /^[A-Za-z]{2}$/.test(value)).map(value => value.toUpperCase())),
    sources: unique(q.getAll('source_filter').filter(value => value.length <= 160)),
    activities: unique(q.getAll('activity').filter(value => value.length <= 240)),
  };
  const source = q.get('source');
  const sourceId = source && /^[A-Za-z0-9.-]{1,80}$/.test(source) ? source : null;
  return { ...DEFAULT_LAB_STATE, direction, scenario, query: q.get('q') ?? '', selectedId: q.get('selected'), sourceId, filters,
    expandedCluster: q.get('cluster') === 'aarhus' ? 'aarhus' : null,
    // Preserve old shared links without preserving a retired map style.
    basemap: q.get('basemap') === 'satellite' ? 'satellite' : 'vector', listOpen: q.get('list') === 'open',
    viewport: { centerLat: safeNumber(q.get('lat'), 45, -90, 90), centerLon: safeNumber(q.get('lon'), 5, -180, 180), zoom: safeNumber(q.get('z'), 2, 1, 18), pitch: safeNumber(q.get('pitch'), 0, 0, 85), bearing: safeNumber(q.get('bearing'), 0, -180, 180) } };
}
export function encodeLabHash(state: LabState, privatePreview = true, publicRelease = false): string {
  const q = new URLSearchParams({ ...(privatePreview ? { f1a: state.direction } : {}), ...(!publicRelease ? { scenario: state.scenario } : {}) });
  const viewport = state.navigationViewport ?? state.viewport;
  // Search input may contain a home address. Keep it in memory rather than
  // browser history or a shareable URL; old q links are still decoded above.
  if (state.selectedId) q.set('selected', state.selectedId);
  if (state.sourceId) q.set('source', state.sourceId);
  if (state.expandedCluster) q.set('cluster', state.expandedCluster);
  if (state.basemap === 'satellite') q.set('basemap', 'satellite'); if (state.listOpen) q.set('list', 'open');
  if (viewport.centerLat !== 45) q.set('lat', String(viewport.centerLat));
  if (viewport.centerLon !== 5) q.set('lon', String(viewport.centerLon));
  if (viewport.zoom !== 2) q.set('z', String(viewport.zoom));
  if (viewport.pitch) q.set('pitch', String(viewport.pitch));
  if (viewport.bearing) q.set('bearing', String(viewport.bearing));
  for (const category of state.filters.categories) q.append('category', category);
  for (const precision of state.filters.precisions) q.append('precision', precision);
  for (const country of state.filters.countries) q.append('country', country);
  for (const source of state.filters.sources) q.append('source_filter', source);
  for (const activity of state.filters.activities) q.append('activity', activity);
  return `#/map?${q.toString()}`;
}
export function encodeMapNavigationHash(databaseHref: string, scenario?: string): string {
  const query = databaseHref.includes('?') ? databaseHref.slice(databaseHref.indexOf('?') + 1) : '';
  const params = new URLSearchParams(query);
  if (scenario) params.set('scenario', scenario);
  else { params.delete('scenario'); params.delete('f1a'); }
  return `#/map?${params.toString()}`;
}
export function reduceLabState(state: LabState, action: LabAction): LabState {
  switch (action.type) {
    case 'direction': return { ...state, direction: action.value };
    case 'scenario': return { ...state, scenario: action.value };
    case 'query': return { ...state, query: action.value, selectedId: null, listOpen: true };
    case 'search': return { ...state, query: action.value.query, filters: { categories: unique(action.value.filters.categories), precisions: unique(action.value.filters.precisions), countries: unique(action.value.filters.countries), sources: unique(action.value.filters.sources), activities: unique(action.value.filters.activities) }, selectedId: null, aggregateMemberIds: null, listOpen: true };
    case 'scope': return isSearchScope(action.value) ? action.preserveWorkspace
      ? { ...state, searchScope: action.value, listOpen: action.value !== null || state.listOpen }
      : { ...state, searchScope: action.value, selectedId: null, aggregateMemberIds: null, listOpen: true } : state;
    case 'results': return { ...state, selectedId: null, listOpen: true };
    case 'close-workspace': return { ...state, selectedId: null, listOpen: false, aggregateMemberIds: null, expandedCluster: null };
    case 'explore-map': {
      const { navigationViewport, ...publicState } = state;
      return { ...publicState, viewport: navigationViewport ?? state.viewport, searchScope: null,
        selectedId: null, listOpen: false, aggregateMemberIds: null, expandedCluster: null };
    }
    case 'select': return { ...state, selectedId: action.value };
    case 'source': return { ...state, sourceId: action.value, selectedId: null, aggregateMemberIds: null };
    case 'cluster': return { ...state, expandedCluster: action.value };
    case 'aggregate': return { ...state, aggregateMemberIds: action.value, listOpen: action.value !== null, selectedId: null };
    case 'basemap': return { ...state, basemap: action.value };
    case 'list': return { ...state, listOpen: action.value };
    case 'viewport': return { ...state, viewport: action.value };
    case 'private-camera': {
      const view = action.value;
      if (![view.centerLat, view.centerLon, view.zoom, view.pitch ?? 0, view.bearing ?? 0].every(Number.isFinite) || Math.abs(view.centerLat) > 90 || Math.abs(view.centerLon) > 180 || view.zoom < 1 || view.zoom > 18 || (view.pitch ?? 0) < 0 || (view.pitch ?? 0) > 85 || Math.abs(view.bearing ?? 0) > 180) return state;
      return { ...state, navigationViewport: state.navigationViewport ?? state.viewport, viewport: view };
    }
    case 'near-device': {
      if (!validDeviceLocation(action.value)) return state;
      const radiusKm = action.value.radiusKm ?? DEFAULT_NEARBY_RADIUS_KM;
      const scope = { kind: 'radius' as const, label: 'Near you', ...action.value, radiusKm, deviceDerived: true as const };
      if (!isSearchScope(scope)) return state;
      return { ...state, navigationViewport: state.navigationViewport ?? state.viewport,
        viewport: { ...state.viewport, centerLat: scope.latitude, centerLon: scope.longitude,
          zoom: nearbyOverviewZoom(radiusKm, scope.latitude) },
        searchScope: scope, selectedId: null, aggregateMemberIds: null, expandedCluster: null, listOpen: true };
    }
    case 'filters': return { ...state, filters: { categories: unique(action.value.categories), precisions: unique(action.value.precisions), countries: unique(action.value.countries), sources: unique(action.value.sources), activities: unique(action.value.activities) } };
    // Retain camera, release, and list state, but clear every active criterion.
    case 'reset-filters': return { ...state, query: '', sourceId: null, filters: DEFAULT_LAB_STATE.filters, searchScope: null, selectedId: null, aggregateMemberIds: null };
  }
}
