import type { LabRecord } from '../design-lab/contract';
import type { ViewportBounds } from '../design-lab/contract';

export type RealPreviewPrecision =
  | 'source_numeric_pending_review'
  | 'approximate_source_provided_pending_review'
  | 'approximate_source_precision_unknown_pending_review'
  | 'city_postal_coarse';

export type RealPreviewCandidate = Readonly<{
  candidateId: string;
  sourceId: string;
  locationClass: 'numeric_source_coordinate' | 'city_postal' | 'unmapped_private_observation';
  displayPrecision: RealPreviewPrecision;
  countryCode: string | null;
  city: string | null;
  postalCode: string | null;
  latitude: number | null;
  longitude: number | null;
  coordinatePrecision: string | null;
  coordinateReviewStatus: string;
  factualReviewStatus: string;
  privacyScreeningStatus: string;
  projectApproval: false;
  publicationStatus: string;
  previewLabel: string;
}>;

export type RealPreviewPage = Readonly<{ records: readonly RealPreviewCandidate[]; nextCursor: string | null }>;
export type RealPreviewCounts = Readonly<{ facilityCandidateCount: number; numericCoordinateCount: number; cityPostalCount: number }>;
export type RealPreviewFacet = Readonly<{ sourceId: string; locationClass: string; count: number }>;

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class RealPreviewError extends Error {
  constructor(readonly kind: 'unauthorized' | 'loopback' | 'not-found' | 'unavailable' | 'network' | 'invalid-response', message: string) {
    super(message);
    this.name = 'RealPreviewError';
  }
}

const API = '/dev/real-preview';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DISPLAY_PRECISIONS = new Set<RealPreviewPrecision>([
  'source_numeric_pending_review',
  'approximate_source_provided_pending_review',
  'approximate_source_precision_unknown_pending_review',
  'city_postal_coarse',
]);

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new RealPreviewError('invalid-response', 'The private preview returned an invalid response.');
  return value as Record<string, unknown>;
}

function nullableString(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'string') throw new RealPreviewError('invalid-response', 'The private preview returned an invalid record.');
  return value;
}

function nullableCoordinate(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new RealPreviewError('invalid-response', 'The private preview returned an invalid coordinate.');
  return value;
}

export function parseRealPreviewCandidate(value: unknown): RealPreviewCandidate {
  const row = object(value);
  const candidateId = row.candidate_id;
  const sourceId = row.source_id;
  const locationClass = row.location_class;
  const displayPrecision = row.display_precision;
  const latitude = nullableCoordinate(row.latitude);
  const longitude = nullableCoordinate(row.longitude);
  if (typeof candidateId !== 'string' || !UUID.test(candidateId)
    || typeof sourceId !== 'string' || !sourceId
    || !['numeric_source_coordinate', 'city_postal', 'unmapped_private_observation'].includes(String(locationClass))
    || typeof displayPrecision !== 'string' || !DISPLAY_PRECISIONS.has(displayPrecision as RealPreviewPrecision)) {
    throw new RealPreviewError('invalid-response', 'The private preview returned an invalid record.');
  }
  const kind = locationClass as RealPreviewCandidate['locationClass'];
  if (latitude === null !== (longitude === null)) throw new RealPreviewError('invalid-response', 'The private preview returned an incomplete coordinate pair.');
  if (latitude !== null && (latitude < -90 || latitude > 90 || longitude! < -180 || longitude! > 180 || (latitude === 0 && longitude === 0))) {
    throw new RealPreviewError('invalid-response', 'The private preview returned an unsafe coordinate.');
  }
  if (kind === 'numeric_source_coordinate' && latitude === null) throw new RealPreviewError('invalid-response', 'The private preview returned a numeric record without coordinates.');
  if (kind !== 'numeric_source_coordinate' && latitude !== null) throw new RealPreviewError('invalid-response', 'The private preview attached a point to a non-numeric record.');
  const projectApproval = row.project_approval;
  if (projectApproval !== false) throw new RealPreviewError('invalid-response', 'The private preview omitted its approval boundary.');
  if (typeof row.coordinate_review_status !== 'string' || typeof row.factual_review_status !== 'string'
    || typeof row.privacy_screening_status !== 'string' || typeof row.publication_status !== 'string'
    || typeof row.preview_label !== 'string') {
    throw new RealPreviewError('invalid-response', 'The private preview omitted its review status.');
  }
  return Object.freeze({
    candidateId, sourceId, locationClass: kind, displayPrecision: displayPrecision as RealPreviewPrecision,
    countryCode: nullableString(row.country_code), city: nullableString(row.city), postalCode: nullableString(row.postal_code),
    latitude, longitude, coordinatePrecision: nullableString(row.coordinate_precision),
    coordinateReviewStatus: row.coordinate_review_status, factualReviewStatus: row.factual_review_status,
    privacyScreeningStatus: row.privacy_screening_status, projectApproval: false,
    publicationStatus: row.publication_status, previewLabel: row.preview_label,
  });
}

export function mapRealPreviewCandidate(candidate: RealPreviewCandidate): LabRecord {
  const precision = candidate.locationClass === 'unmapped_private_observation' ? 'unmapped'
    : candidate.locationClass === 'city_postal' || candidate.displayPrecision === 'city_postal_coarse' ? 'coarse'
      : candidate.displayPrecision === 'source_numeric_pending_review' ? 'exact' : 'approximate';
  const place = candidate.city ?? candidate.postalCode ?? candidate.countryCode ?? 'Unmapped candidate';
  return Object.freeze({
    id: candidate.candidateId,
    name: `${place} · ${candidate.sourceId}`,
    category: 'Facility candidate',
    country: candidate.countryCode ?? 'Unknown country',
    locality: candidate.city ?? candidate.postalCode ?? 'No mapped locality',
    precision,
    latitude: candidate.latitude,
    longitude: candidate.longitude,
    sourceId: candidate.sourceId,
    reviewStatus: candidate.coordinateReviewStatus,
    previewLabel: candidate.previewLabel,
  });
}

export function createRealPreviewRepository(fetcher: FetchLike = fetch): {
  list(options?: { query?: string; cursor?: string | null; limit?: number; signal?: AbortSignal }): Promise<RealPreviewPage>;
  viewport(bounds: ViewportBounds, options?: { cursor?: string | null; limit?: number; signal?: AbortSignal }): Promise<RealPreviewPage>;
  detail(id: string, signal?: AbortSignal): Promise<RealPreviewCandidate>;
  counts(signal?: AbortSignal): Promise<RealPreviewCounts>;
  facets(signal?: AbortSignal): Promise<readonly RealPreviewFacet[]>;
} {
  async function request<T>(path: string, signal?: AbortSignal, parse?: (body: unknown) => T): Promise<T> {
    let response: Response;
    try {
      const init: RequestInit = { method: 'GET', cache: 'no-store', headers: { Accept: 'application/json' } };
      if (signal) init.signal = signal;
      response = await fetcher(`${API}${path}`, init);
    } catch (error) {
      if (signal?.aborted) throw error;
      throw new RealPreviewError('network', 'The private real-data preview could not be reached. Start it again and retry.');
    }
    if (response.status === 401) throw new RealPreviewError('unauthorized', 'Private preview authentication failed. Restart the local real-preview command and try again.');
    if (response.status === 403) throw new RealPreviewError('loopback', 'The private preview is available only from its local loopback address.');
    if (response.status === 404) throw new RealPreviewError('not-found', 'This private preview record is no longer available.');
    if (response.status >= 500) throw new RealPreviewError('unavailable', 'The private preview data service is unavailable.');
    if (!response.ok) throw new RealPreviewError('invalid-response', 'The private preview request was rejected.');
    try {
      const body: unknown = await response.json();
      return parse ? parse(body) : body as T;
    } catch (error) {
      if (error instanceof RealPreviewError) throw error;
      throw new RealPreviewError('invalid-response', 'The private preview returned an invalid response.');
    }
  }
  const parsePage = (body: unknown): RealPreviewPage => {
    const envelope = object(body);
    if (envelope.api_version !== 'real-preview-v1' || !Array.isArray(envelope.data)) throw new RealPreviewError('invalid-response', 'The private preview returned an invalid page.');
    const meta = object(envelope.meta);
    if (meta.private_preview !== true || (meta.next_cursor !== null && typeof meta.next_cursor !== 'string')) throw new RealPreviewError('invalid-response', 'The private preview returned invalid paging metadata.');
    return Object.freeze({ records: Object.freeze(envelope.data.map(parseRealPreviewCandidate)), nextCursor: meta.next_cursor as string | null });
  };
  return {
    list({ query = '', cursor = null, limit = 200, signal } = {}) {
      const params = new URLSearchParams({ limit: String(limit) });
      if (query.trim()) params.set('q', query.trim().slice(0, 100));
      if (cursor) params.set('cursor', cursor);
      return request(`/locations?${params}`, signal, parsePage);
    },
    viewport(bounds, { cursor = null, limit = 500, signal } = {}) {
      const params = new URLSearchParams({ west: String(bounds.west), south: String(bounds.south), east: String(bounds.east), north: String(bounds.north), limit: String(limit) });
      if (cursor) params.set('cursor', cursor);
      return request(`/viewport?${params}`, signal, parsePage);
    },
    detail(id, signal) {
      if (!UUID.test(id)) return Promise.reject(new RealPreviewError('not-found', 'This private preview record is no longer available.'));
      return request(`/locations/${encodeURIComponent(id)}`, signal, body => {
        const envelope = object(body);
        if (envelope.api_version !== 'real-preview-v1') throw new RealPreviewError('invalid-response', 'The private preview returned an invalid record.');
        return parseRealPreviewCandidate(object(envelope.data));
      });
    },
    counts(signal) {
      return request('/counts', signal, body => {
        const envelope = object(body);
        const data = object(envelope.data);
        const values = [data.facility_candidate_count, data.numeric_coordinate_count, data.city_postal_count];
        if (envelope.api_version !== 'real-preview-v1' || !values.every(value => Number.isInteger(value) && Number(value) >= 0)) throw new RealPreviewError('invalid-response', 'The private preview returned invalid counts.');
        return Object.freeze({ facilityCandidateCount: Number(values[0]), numericCoordinateCount: Number(values[1]), cityPostalCount: Number(values[2]) });
      });
    },
    facets(signal) {
      return request('/facets', signal, body => {
        const envelope = object(body);
        if (envelope.api_version !== 'real-preview-v1' || !Array.isArray(envelope.data)) throw new RealPreviewError('invalid-response', 'The private preview returned invalid source summaries.');
        return Object.freeze(envelope.data.map(item => {
          const row = object(item);
          if (typeof row.source_id !== 'string' || typeof row.location_class !== 'string' || !Number.isInteger(row.count) || Number(row.count) < 0) throw new RealPreviewError('invalid-response', 'The private preview returned invalid source summaries.');
          return Object.freeze({ sourceId: row.source_id, locationClass: row.location_class, count: Number(row.count) });
        }));
      });
    },
  };
}
