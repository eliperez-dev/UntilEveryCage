export const DIRECTIONS = ['atlas', 'index', 'field'] as const;
export const SCENARIOS = ['default', 'dense', 'loading', 'empty', 'error', 'mobile'] as const;
export type Direction = (typeof DIRECTIONS)[number];
export type Scenario = (typeof SCENARIOS)[number];
export type Precision = 'exact' | 'city' | 'coarse' | 'unmapped';
export type Basemap = 'vector' | 'satellite';
export type LabFilters = Readonly<{ categories: readonly string[]; precisions: readonly Precision[] }>;

export type LabRecord = Readonly<{
  id: string; name: string; category: string; country: string; locality: string;
  precision: Precision; latitude: number | null; longitude: number | null;
}>;
export type Viewport = Readonly<{ centerLat: number; centerLon: number; zoom: number }>;
export type LabState = Readonly<{
  direction: Direction; scenario: Scenario; query: string; selectedId: string | null;
  expandedCluster: string | null; basemap: Basemap; listOpen: boolean; viewport: Viewport;
  filters: LabFilters;
}>;
export type LabAction =
  | { type: 'direction'; value: Direction } | { type: 'scenario'; value: Scenario }
  | { type: 'query'; value: string } | { type: 'select'; value: string | null }
  | { type: 'cluster'; value: string | null } | { type: 'basemap'; value: Basemap }
  | { type: 'list'; value: boolean } | { type: 'viewport'; value: Viewport }
  | { type: 'filters'; value: LabFilters } | { type: 'reset-filters' };

export interface DirectionViewProps { state: LabState; records: readonly LabRecord[]; dispatch(action: LabAction): void }

export const DEFAULT_LAB_STATE: LabState = Object.freeze({
  direction: 'atlas', scenario: 'default', query: '', selectedId: null,
  expandedCluster: null, basemap: 'vector', listOpen: true,
  viewport: Object.freeze({ centerLat: 45, centerLon: 5, zoom: 2 }),
  filters: Object.freeze({ categories: Object.freeze([]), precisions: Object.freeze([]) }),
});
