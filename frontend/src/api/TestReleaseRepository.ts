import { z } from 'zod';
import { testReleaseLocationSchema, type WireLocation } from './wireSchema';
import { mapWireLocation, type FetchLike } from './LocalLocationRepository';
import type { Location } from '../domain/location';
import { TEST_RELEASE_API_VERSION, TEST_RELEASE_PATH } from '../features/devPreview/devPreviewContract';

const metaSchema = z.object({ api_version: z.literal(TEST_RELEASE_API_VERSION), private_preview: z.literal(true), candidate_only: z.literal(true), test_only: z.literal(false), release_id: z.string().min(1), snapshot_id: z.string().regex(/^[a-f0-9]{64}$/), preview_label: z.string().min(1), result_count: z.number().int().nonnegative(), total_count: z.number().int().nonnegative(), next_cursor: z.string().uuid().nullable() }).strict();
const envelope = z.object({ data: z.array(testReleaseLocationSchema), meta: metaSchema }).strict();
const facetMetaSchema = z.object({ api_version: z.literal(TEST_RELEASE_API_VERSION), private_preview: z.literal(true), candidate_only: z.literal(true), test_only: z.literal(false), release_id: z.string().min(1), preview_label: z.string().min(1), result_count: z.number().int().nonnegative() }).passthrough();
const facetValue = z.object({ value: z.string().min(1), count: z.number().int().nonnegative() }).strict();
const facetsEnvelope = z.object({ data: z.null(), meta: facetMetaSchema, dimensions: z.object({ country_code: z.array(facetValue), category: z.array(facetValue), display_precision: z.array(facetValue), source_type: z.array(facetValue), source_id: z.array(facetValue) }).strict() }).strict();
export type CandidateListOptions = Readonly<{ q?: string; sourceId?: string; countryCode?: string; category?: string; cursor?: string | null; limit?: number; signal?: AbortSignal }>;
export type CandidateListResult = Readonly<{ locations: readonly Location[]; releaseId: string; snapshotId: string; previewLabel: string; totalCount: number; nextCursor: string | null }>;
export type CandidateFacets = Readonly<{ sources: readonly Readonly<{ value: string; count: number }>[]; countries: readonly Readonly<{ value: string; count: number }>[]; categories: readonly Readonly<{ value: string; count: number }>[] }>;

/** Configured private correction candidate. Credentials are injected by Vite's loopback proxy. */
export class TestReleaseRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, private readonly baseUrl = '') {}
  async list({ q, sourceId, countryCode, category, cursor, limit = 100, signal }: CandidateListOptions = {}): Promise<CandidateListResult> {
    const params = new URLSearchParams({ profile: 'official', limit: String(Math.max(1, Math.min(1000, limit))) });
    if (q?.trim()) params.set('q', q.trim());
    if (sourceId?.trim()) params.set('source_id', sourceId.trim());
    if (countryCode && /^[A-Za-z]{2}$/.test(countryCode)) params.set('country_code', countryCode.toUpperCase());
    if (category) params.set('category', category);
    if (cursor) params.set('cursor', cursor);
    const init: RequestInit = { cache: 'no-store', credentials: 'same-origin', ...(signal ? { signal } : {}) };
    const response = await this.fetcher.call(globalThis, `${this.baseUrl}${TEST_RELEASE_PATH}/locations?${params}`, init);
    if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'The configured candidate session is not authorized.' : `The configured candidate list could not be loaded (HTTP ${response.status}).`);
    const parsed = envelope.safeParse(await response.json());
    if (!parsed.success || parsed.data.meta.result_count !== parsed.data.data.length) throw new Error('The configured candidate list was rejected safely.');
    const data = parsed.data;
    return { locations: data.data.map(row => mapWireLocation({ ...row, project_approval: row.project_approval === 'not-approved' ? false : row.project_approval } as WireLocation)), releaseId: data.meta.release_id, snapshotId: data.meta.snapshot_id, previewLabel: data.meta.preview_label, totalCount: data.meta.total_count, nextCursor: data.meta.next_cursor };
  }
  async facets(signal?: AbortSignal): Promise<CandidateFacets> {
    const response = await this.fetcher.call(globalThis, `${this.baseUrl}${TEST_RELEASE_PATH}/discovery/facets`, { cache: 'no-store', credentials: 'same-origin', ...(signal ? { signal } : {}) });
    if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'The configured candidate session is not authorized.' : 'The configured candidate facets could not be loaded.');
    const parsed = facetsEnvelope.safeParse(await response.json());
    if (!parsed.success) throw new Error('The configured candidate facets were rejected safely.');
    return { sources: parsed.data.dimensions.source_id, countries: parsed.data.dimensions.country_code, categories: parsed.data.dimensions.category };
  }
}
