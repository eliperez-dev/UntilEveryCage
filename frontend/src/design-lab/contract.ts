export const DIRECTIONS = ['field'] as const;
export const SCENARIOS = ['default', 'dense', 'loading', 'empty', 'error', 'mobile'] as const;
export type Direction = (typeof DIRECTIONS)[number];
export type Scenario = (typeof SCENARIOS)[number];
export type Precision = 'exact' | 'source_reported' | 'approximate' | 'city' | 'coarse' | 'unmapped';
export type Basemap = 'vector' | 'muted' | 'satellite';
export type LabFilters = Readonly<{ categories: readonly string[]; precisions: readonly Precision[]; countries: readonly string[]; sources: readonly string[]; activities: readonly string[] }>;

export type LabRecord = Readonly<{
  id: string; name: string; category: string; country: string; locality: string;
  precision: Precision; latitude: number | null; longitude: number | null;
  sourceId?: string; reviewStatus?: string; previewLabel?: string; coordinatePrecision?: string | null; coordinateProvenance?: string | null;
  facilityAddress?: string | null; coordinateMethod?: string | null; coordinateProvider?: string | null;
  coordinateConfidence?: number | null; coordinateConfidenceBand?: 'high' | 'medium' | 'low' | null;
  defaultMapScope?: boolean; mapScopeReason?: string | null;
  factualReviewStatus?: string; privacyScreeningStatus?: string; publicationStatus?: string;
  projectApproval?: boolean;
  taxonomy?: import('../domain/taxonomy').TaxonomyClassification;
  sourceName?: string | null;
  sourceUrl?: string | null;
  sourceLocationRole?: 'aphis_mailing_locality' | null;
  retrievedAt?: string | null;
  observedAt?: string | null;
  sourceFacts?: import('../domain/location').LocationSourceFacts | undefined;
}>;
export type ViewportBounds = Readonly<{ west: number; south: number; east: number; north: number }>;
/** Aggregate-only view of the complete identity-validated mapped result set. */
export type AreaSummary = Readonly<{
  status: 'loading' | 'ready' | 'error';
  total: number;
  categories: readonly Readonly<{ key: import('../domain/taxonomy').TaxonomyPrimaryKey; count: number }>[];
  sourceCount: number;
  sourceReportedCount: number;
  approximateCount: number;
  bounds: ViewportBounds | null;
}>;
/** Consumed once; never encoded in a route or browser storage. */
export type NearbySearchCommand = Readonly<{ id: number; latitude: number; longitude: number }>;
export type SearchScope = null
  | Readonly<{ kind: 'area'; bounds: ViewportBounds }>
  | Readonly<{ kind: 'radius'; label: string; latitude: number; longitude: number; radiusKm: number; deviceDerived?: true }>;
export type Viewport = Readonly<{ centerLat: number; centerLon: number; zoom: number; pitch?: number; bearing?: number }>;
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
  searchScope: SearchScope;
  /** Memory-only camera to use in links while the live view follows device location. */
  navigationViewport?: Viewport;
}>;
export type LabAction =
  | { type: 'direction'; value: Direction } | { type: 'scenario'; value: Scenario }
  | { type: 'query'; value: string } | { type: 'select'; value: string | null } | { type: 'source'; value: string | null }
  | { type: 'cluster'; value: string | null } | { type: 'aggregate'; value: readonly string[] | null } | { type: 'basemap'; value: Basemap }
  | { type: 'list'; value: boolean } | { type: 'viewport'; value: Viewport }
  | { type: 'private-camera'; value: Viewport }
  | { type: 'near-device'; value: Readonly<{ latitude: number; longitude: number; radiusKm?: number }> }
  | { type: 'filters'; value: LabFilters } | { type: 'reset-filters' }
  | { type: 'scope'; value: SearchScope; preserveWorkspace?: boolean }
  | { type: 'search'; value: { query: string; filters: LabFilters } }
  | { type: 'results' } | { type: 'close-workspace' };

export type PinHoverLabel = Readonly<{ name: string; categoryKey: string }>;
export type MapDisplaySettings = Readonly<{ clusterMode: 'auto' | 'on' | 'off'; pinScale: number; optimizedPins: boolean; coordinateRadius: number }>;
export type MapDisplaySettingsRequest = Readonly<{ id: number; patch: Partial<MapDisplaySettings> }>;

export interface DirectionViewProps {
  state: LabState;
  records: readonly LabRecord[];
  mapRecords?: readonly LabRecord[];
  resolvePinHover?(id: string, signal: AbortSignal): Promise<PinHoverLabel | null>;
  mode?: 'synthetic' | 'real-preview' | 'candidate-preview' | 'public-release';
  publicReleaseId?: string | null;
  publicReleaseIdentity?: string | null;
  publicReleaseManifestIdentity?: import('../api/PublicReleaseRepository').PublicReleaseIdentity | null;
  publicMapMeta?: import('../api/PublicMapFeedRepository').PublicMapFeed['meta'] | null;
  onMapFeedMeta?: ((meta: import('../api/PublicMapFeedRepository').PublicMapFeed['meta'] | null) => void) | undefined;
  onCandidatePreviewLabel?: ((label: string | null) => void) | undefined;
  candidateFacets?: import('../api/TestReleaseRepository').CandidateFacets | null;
  dataStatus?: 'loading' | 'ready' | 'empty' | 'error' | 'unauthorized';
  dataError?: string;
  mapStatus?: 'idle' | 'loading' | 'ready' | 'empty' | 'error' | 'unauthorized';
  mapError?: string;
  mapTruncated?: boolean;
  mapMatchingIds?: readonly string[] | null;
  mapMatchesSearchKey?: string | null;
  mapMatchesTotalCount?: number | null;
  mapMatchesMappedCount?: number | null;
  mapMatchesStatus?: 'idle' | 'loading' | 'ready' | 'error';
  mapMatchesError?: string;
  onRetryMapMatches?(): void;
  mapDiagnostics?: MapDiagnostics;
  onMapTiming?(timing: MapTiming): void;
  detailRecord?: LabRecord | null;
  detailStatus?: 'loading' | 'ready' | 'error' | 'unauthorized';
  detailError?: string;
  nextCursor?: string | null;
  pageLoading?: boolean;
  listRefreshing?: boolean;
  onLoadMore?(): void;
  /** Resolves an opaque administrative-reference key emitted by the private map feed. */
  onMapReference?(key: string, sourceId?: string): void;
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
  expandedCluster: null, aggregateMemberIds: null, basemap: 'vector', listOpen: false, searchScope: null,
  viewport: Object.freeze({ centerLat: 45, centerLon: 5, zoom: 2 }),
  filters: Object.freeze({ categories: Object.freeze([]), precisions: Object.freeze([]), countries: Object.freeze([]), sources: Object.freeze([]), activities: Object.freeze([]) }),
});
