import { z } from 'zod';
import { testReleaseLocationSchema, type WireLocation } from './wireSchema';
import { mapWireLocation, type FetchLike } from './LocalLocationRepository';
import type { Location } from '../domain/location';
import { TEST_RELEASE_API_VERSION, TEST_RELEASE_PATH } from '../features/devPreview/devPreviewContract';

const candidateMeta = z.object({
  api_version: z.literal(TEST_RELEASE_API_VERSION), private_preview: z.literal(true), candidate_only: z.literal(true), test_only: z.literal(false),
  environment: z.literal('private-candidate-preview'), release_status: z.literal('candidate'), release_id: z.string().min(1), profile: z.literal('official'),
  coverage_scope: z.string().min(1), count_semantics: z.string().min(1), preview_label: z.string().min(1), result_count: z.number().int().nonnegative(),
}).passthrough();
const metaSchema = candidateMeta.extend({ total_count: z.number().int().nonnegative(), next_cursor: z.string().uuid().nullable() });
const envelope = z.object({ data: z.array(testReleaseLocationSchema), meta: metaSchema }).strict();
const facetMetaSchema = candidateMeta;
const facetValue = z.object({ value: z.string().min(1), label: z.string().min(1).optional(), count: z.number().int().nonnegative() }).strict();
const facetsEnvelope = z.object({ data: z.null(), meta: facetMetaSchema, dimensions: z.object({ country_code: z.array(facetValue), category: z.array(facetValue), activity: z.array(facetValue).optional().default([]), display_precision: z.array(facetValue), source_type: z.array(facetValue), source_id: z.array(facetValue) }).strict() }).strict();
export type CandidateListOptions = Readonly<{ q?: string; sourceIds?: readonly string[]; countryCodes?: readonly string[]; categories?: readonly string[]; activities?: readonly string[]; /** Compatibility aliases while callers migrate to multi-value filters. */ sourceId?: string; countryCode?: string; category?: string; cursor?: string | null; limit?: number; signal?: AbortSignal }>;
export type CandidateListResult = Readonly<{ locations: readonly Location[]; releaseId: string; previewLabel: string; totalCount: number; nextCursor: string | null }>;
export type CandidateFacet = Readonly<{ value: string; label: string | undefined; count: number }>;
export type CandidateFacets = Readonly<{ sources: readonly CandidateFacet[]; countries: readonly CandidateFacet[]; categories: readonly CandidateFacet[]; activities: readonly CandidateFacet[] }>;

/** Configured private correction candidate. Credentials are injected by Vite's loopback proxy. */
export class TestReleaseRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, private readonly baseUrl = '') {}
  async list({ q, sourceIds, countryCodes, categories, activities, sourceId, countryCode, category, cursor, limit = 100, signal }: CandidateListOptions = {}): Promise<CandidateListResult> {
    const params = new URLSearchParams({ profile: 'official', limit: String(Math.max(1, Math.min(1000, limit))) });
    if (q?.trim()) params.set('q', q.trim());
    const csv = (values: readonly string[] | undefined, compatibility: string | undefined, valid: (value: string) => boolean) => [...new Set([...(values ?? []), ...(compatibility ? [compatibility] : [])].map(value => value.trim()).filter(valid))].join(',');
    const sources = csv(sourceIds, sourceId, value => value.length <= 160);
    const countries = csv(countryCodes, countryCode, value => /^[A-Za-z]{2}$/.test(value)).toUpperCase();
    const categoryValues = csv(categories, category, value => value.length <= 120);
    const activityValues = csv(activities, undefined, value => value.length <= 240);
    if (sources) params.set('source_id', sources);
    if (countries) params.set('country_code', countries);
    if (categoryValues) params.set('category', categoryValues);
    if (activityValues) params.set('activity', activityValues);
    if (cursor) params.set('cursor', cursor);
    const init: RequestInit = { cache: 'no-store', credentials: 'same-origin', ...(signal ? { signal } : {}) };
    const response = await this.fetcher.call(globalThis, `${this.baseUrl}${TEST_RELEASE_PATH}/locations?${params}`, init);
    if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'The configured candidate session is not authorized.' : `The configured candidate list could not be loaded (HTTP ${response.status}).`);
    const parsed = envelope.safeParse(await response.json());
    if (!parsed.success || parsed.data.meta.result_count !== parsed.data.data.length || parsed.data.data.some(row => row.release_id !== parsed.data.meta.release_id)) throw new Error('The configured candidate list was rejected safely.');
    const data = parsed.data;
    return { locations: data.data.map(row => mapWireLocation({ ...row, project_approval: row.project_approval === 'not-approved' ? false : row.project_approval } as WireLocation)), releaseId: data.meta.release_id, previewLabel: data.meta.preview_label, totalCount: data.meta.total_count, nextCursor: data.meta.next_cursor };
  }
  async facets(signal?: AbortSignal): Promise<CandidateFacets> {
    const response = await this.fetcher.call(globalThis, `${this.baseUrl}${TEST_RELEASE_PATH}/discovery/facets`, { cache: 'no-store', credentials: 'same-origin', ...(signal ? { signal } : {}) });
    if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'The configured candidate session is not authorized.' : 'The configured candidate facets could not be loaded.');
    const parsed = facetsEnvelope.safeParse(await response.json());
    if (!parsed.success) throw new Error('The configured candidate facets were rejected safely.');
    const facets = (values: readonly { value: string; count: number; label?: string | undefined }[]): readonly CandidateFacet[] => values.map(({ value, count, label }) => ({ value, count, label }));
    return { sources: facets(parsed.data.dimensions.source_id), countries: facets(parsed.data.dimensions.country_code), categories: facets(parsed.data.dimensions.category), activities: facets(parsed.data.dimensions.activity) };
  }
}
