import { z } from 'zod';
import type { FetchLike } from './LocalLocationRepository';
import type { Location } from '../domain/location';
import { DEV_PREVIEW_PATH, DEV_PREVIEW_TOKEN_HEADER } from '../features/devPreview/devPreviewContract';

const rowSchema = z.object({
  candidate_id: z.string().min(1), source_record_id: z.string().min(1), facility_id: z.string().min(1), canonical_name: z.string().min(1),
  country_code: z.string().min(1), city: z.string().nullable(), category: z.string().min(1), display_precision: z.enum(['exact', 'city', 'unmapped']),
  latitude: z.number().finite().nullable(), longitude: z.number().finite().nullable(), source_type: z.enum(['official', 'secondary', 'user_submitted']),
  provenance_source_id: z.string().min(1), provenance_source_name: z.string().min(1), provenance_source_url: z.string().url().refine(value => { try { return ['http:', 'https:'].includes(new URL(value).protocol); } catch { return false; } }, 'source URL must use HTTP or HTTPS'), provenance_retrieved_at: z.string().min(1),
  factual_review_status: z.enum(['unreviewed', 'reviewed', 'rejected']), privacy_screening_status: z.literal('passed'), project_approval: z.literal(false),
  release_id: z.string().nullable(), release_status: z.literal('candidate'), preview_label: z.string().min(1),
}).superRefine((row, ctx) => { if ((row.latitude === null) !== (row.longitude === null)) ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'coordinate pair must be complete' }); });
const envelopeSchema = z.object({ api_version: z.literal('dev-preview-v1'), data: z.array(rowSchema), meta: z.object({ test_only: z.literal(true), private_preview: z.literal(true), profile: z.null(), coverage_scope: z.literal('candidate_release_only'), next_cursor: z.null() }) });

export type DevCandidate = Location & Readonly<{ candidateId: string; sourceRecordId: string; previewLabel: string; releaseStatus: 'candidate'; coverageScope: string }>;

/** Token is accepted only as an in-memory argument; callers must not persist or put it in a URL. */
export class DevCandidatePreviewRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, private readonly baseUrl = '') {}
  async list(token: string, signal?: AbortSignal): Promise<readonly DevCandidate[]> {
    if (!token.trim()) throw new Error('An operator token is required for the private candidate preview.');
    const init: RequestInit = { cache: 'no-store', headers: { [DEV_PREVIEW_TOKEN_HEADER]: token } };
    if (signal) init.signal = signal;
    const response = await this.fetcher.call(globalThis, `${this.baseUrl}${DEV_PREVIEW_PATH}?limit=100`, init);
    if (!response.ok) throw new Error(response.status === 401 ? 'Private candidate preview authentication failed.' : response.status === 404 ? 'Private candidate preview is disabled.' : `Private candidate preview failed with status ${response.status}.`);
    const parsed = envelopeSchema.safeParse(await response.json());
    if (!parsed.success) throw new Error('Private candidate preview response was rejected safely.');
    return parsed.data.data.map((row) => ({
      id: row.facility_id, name: row.canonical_name, region: row.city ?? row.country_code, category: row.category,
      lat: row.latitude, lon: row.longitude, observed: 'candidate observation date unavailable', source: row.provenance_source_name,
      candidateId: row.candidate_id, sourceRecordId: row.source_record_id, previewLabel: row.preview_label, releaseStatus: row.release_status, coverageScope: parsed.data.meta.coverage_scope,
      evidence: { sourceType: row.source_type, factualReviewStatus: row.factual_review_status, reviewerRole: null, privacyScreeningStatus: row.privacy_screening_status, projectApproval: false, publicationProfile: null, publicationWarning: row.preview_label, sourceId: row.provenance_source_id, sourceUrl: row.provenance_source_url, provenanceSource: null, sourceRightsStatus: 'unknown', retrievedAt: row.provenance_retrieved_at, displayPrecision: row.display_precision, lifecycleStatus: 'status_unknown', observationCount: null },
    }));
  }
}
