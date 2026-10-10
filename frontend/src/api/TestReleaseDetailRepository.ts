import { testReleaseDetailLocationSchema, type WireTestReleaseDetailLocation } from './wireSchema';
import type { FetchLike } from './LocalLocationRepository';
import type { LabRecord, Precision } from '../design-lab/contract';
import type { LocationSourceFacts } from '../domain/location';
import { TEST_RELEASE_API_VERSION, TEST_RELEASE_PATH } from '../features/devPreview/devPreviewContract';
import { RealPreviewError } from './RealPreviewRepository';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const precision = (value: WireTestReleaseDetailLocation['display_precision']): Precision =>
  value === 'source_reported' ? 'source_reported' : value === 'exact' || value === 'city' || value === 'approximate' || value === 'unmapped' ? value : 'unmapped';

function sourceFacts(row: WireTestReleaseDetailLocation): LocationSourceFacts | undefined {
  const facts: LocationSourceFacts = {
    ...(row.alternate_names ? { alternateNames: row.alternate_names } : {}),
    ...(row.species_slaughtered ? { speciesSlaughtered: row.species_slaughtered } : {}),
    ...(row.processing_activities ? { processingActivities: row.processing_activities } : {}),
    ...(row.source_volume_categories ? { sourceVolumeCategories: row.source_volume_categories.map(category => ({
      code: category.code,
      ...(category.provenance === undefined ? {} : { provenance: typeof category.provenance === 'string'
        ? category.provenance
        : { ...(category.provenance.source_field ? { sourceField: category.provenance.source_field } : {}), ...(category.provenance.method ? { method: category.provenance.method } : {}) } }),
    })) } : {}),
    ...(row.establishment_id ? { establishmentId: row.establishment_id } : {}),
    ...(row.establishment_number ? { establishmentNumber: row.establishment_number } : {}),
    ...(row.grant_date ? { grantDate: row.grant_date } : {}),
    ...(row.native_activity_code ? { nativeActivityCode: row.native_activity_code } : {}),
    ...(row.native_activity_label ? { nativeActivityLabel: row.native_activity_label } : {}),
  };
  return Object.keys(facts).length ? facts : undefined;
}

export function mapTestReleaseDetail(row: WireTestReleaseDetailLocation): LabRecord {
  const facts = sourceFacts(row);
  return {
    id: row.facility_id,
    name: row.canonical_name ?? 'Name not provided',
    category: row.category,
    country: row.country_code,
    locality: row.city ?? row.country_code,
    precision: precision(row.display_precision),
    latitude: row.latitude,
    longitude: row.longitude,
    sourceId: row.provenance_source_id,
    sourceName: row.provenance_source_name,
    sourceUrl: row.provenance_source_url,
    retrievedAt: row.provenance_retrieved_at,
    factualReviewStatus: row.factual_review_status,
    privacyScreeningStatus: row.privacy_screening_status,
    projectApproval: row.project_approval === 'approved',
    ...(facts ? { sourceFacts: facts } : {}),
  };
}

/** Private configured-candidate detail. This endpoint is never used by V0. */
export class TestReleaseDetailRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, private readonly baseUrl = '') {}

  async detail(id: string, signal?: AbortSignal): Promise<LabRecord> {
    if (!UUID.test(id)) throw new RealPreviewError('not-found', 'This corrected candidate record is no longer available.');
    let response: Response;
    try {
      response = await this.fetcher.call(globalThis, `${this.baseUrl}${TEST_RELEASE_PATH}/locations/${encodeURIComponent(id)}`, {
        credentials: 'same-origin', cache: 'no-store', ...(signal ? { signal } : {}),
      });
    } catch {
      throw new RealPreviewError('network', 'The corrected candidate detail could not be reached.');
    }
    if (!response.ok) throw new RealPreviewError(response.status === 401 || response.status === 403 ? 'unauthorized' : 'invalid-response', response.status === 401 || response.status === 403 ? 'The corrected candidate session is not authorized.' : 'The corrected candidate detail could not be loaded.');
    const payload = await response.json();
    const parsed = testReleaseDetailLocationSchema.safeParse((payload as { data?: unknown }).data);
    if (!payload || typeof payload !== 'object' || (payload as { api_version?: unknown }).api_version !== TEST_RELEASE_API_VERSION || !parsed.success || parsed.data.facility_id !== id) {
      throw new RealPreviewError('invalid-response', 'The corrected candidate detail was rejected safely.');
    }
    return mapTestReleaseDetail(parsed.data);
  }
}
