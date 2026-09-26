export const DIRECTIONS = ['field'] as const;
export const SCENARIOS = ['default', 'dense', 'loading', 'empty', 'error', 'mobile'] as const;
export type Direction = (typeof DIRECTIONS)[number];
export type Scenario = (typeof SCENARIOS)[number];
export type Precision = 'exact' | 'approximate' | 'city' | 'coarse' | 'unmapped';
export type Basemap = 'vector' | 'satellite';
export type LabFilters = Readonly<{ categories: readonly string[]; precisions: readonly Precision[] }>;

export type LabRecord = Readonly<{
  id: string; name: string; category: string; country: string; locality: string;
  precision: Precision; latitude: number | null; longitude: number | null;
  sourceId?: string; reviewStatus?: string; previewLabel?: string; coordinatePrecision?: string | null; coordinateProvenance?: string | null;
  defaultMapScope?: boolean; mapScopeReason?: string | null;
  factualReviewStatus?: string; privacyScreeningStatus?: string; publicationStatus?: string;
  projectApproval?: boolean;
}>;
export type ViewportBounds = Readonly<{ west: number; south: number; east: number; north: number }>;
export type Viewport = Readonly<{ centerLat: number; centerLon: number; zoom: number }>;
export type MapDiagnostics = Readonly<{
  zoom: number; currentTiles: number; readyTiles: number; cacheEntries: number; cacheCapacity: number;
  cacheHits: number; cacheMisses: number; inFlight: number; lastFetchMs: number | null;
  renderedRecords: number; sourceId: string | null; truncated: boolean;
  sourceMaterializeMs: number | null; clusterReadyMs: number | null; zoomSettleMs: number | null;
}>;
export type MapTiming = Readonly<{ sourceMaterializeMs: number; clusterReadyMs: number | null; sourceFeatureCount: number; zoomSettleMs?: number | null }>;
export type LabState = Readonly<{
  direction: Direction; scenario: Scenario; query: string; selectedId: string | null;
  sourceId: string | null;
  expandedCluster: string | null; aggregateMemberIds: readonly string[] | null; basemap: Basemap; listOpen: boolean; viewport: Viewport;
  filters: LabFilters;
}>;
export type LabAction =
  | { type: 'direction'; value: Direction } | { type: 'scenario'; value: Scenario }
  | { type: 'query'; value: string } | { type: 'select'; value: string | null } | { type: 'source'; value: string | null }
  | { type: 'cluster'; value: string | null } | { type: 'aggregate'; value: readonly string[] | null } | { type: 'basemap'; value: Basemap }
  | { type: 'list'; value: boolean } | { type: 'viewport'; value: Viewport }
  | { type: 'filters'; value: LabFilters } | { type: 'reset-filters' };

export interface DirectionViewProps {
  state: LabState;
  records: readonly LabRecord[];
  mapRecords?: readonly LabRecord[];
  mode?: 'synthetic' | 'real-preview';
  dataStatus?: 'loading' | 'ready' | 'empty' | 'error' | 'unauthorized';
  dataError?: string;
  mapStatus?: 'idle' | 'loading' | 'ready' | 'empty' | 'error' | 'unauthorized';
  mapError?: string;
  mapTruncated?: boolean;
  mapDiagnostics?: MapDiagnostics;
  /** Use the local server's lightweight MVT map projection instead of the
   * bounded JSON viewport fallback.  This is deliberately opt-in while the
   * preview tile route is being smoke tested. */
  useMvtMap?: boolean;
  onMapTiming?(timing: MapTiming): void;
  detailRecord?: LabRecord | null;
  detailStatus?: 'loading' | 'ready' | 'error' | 'unauthorized';
  detailError?: string;
  nextCursor?: string | null;
  pageLoading?: boolean;
  onLoadMore?(): void;
  /** Resolves an opaque administrative-reference key emitted only by the local MVT projection. */
  onMapReference?(key: string): void;
  aggregateMemberRecords?: readonly LabRecord[];
  aggregateNextCursor?: string | null;
  aggregateLoading?: boolean;
  aggregateError?: string;
  onLoadMoreAggregate?(): void;
  onViewportBounds?(bounds: ViewportBounds): void;
  dispatch(action: LabAction): void;
}

export const DEFAULT_LAB_STATE: LabState = Object.freeze({
  direction: 'field', scenario: 'default', query: '', selectedId: null, sourceId: null,
  expandedCluster: null, aggregateMemberIds: null, basemap: 'vector', listOpen: false,
  viewport: Object.freeze({ centerLat: 45, centerLon: 5, zoom: 2 }),
  filters: Object.freeze({ categories: Object.freeze([]), precisions: Object.freeze([]) }),
});
