import { z } from 'zod';
import type { FetchLike, LocalProfile } from './LocalLocationRepository';
import type { ApiError } from './errors';

const facet = z.object({ value: z.string(), count: z.number().int().nonnegative() });
const responseSchema = z.object({ api_version: z.literal('v2'), meta: z.object({ profile: z.enum(['official', 'secondary', 'community']), release_id: z.string(), ruleset_version: z.string(), release_created_at: z.string(), coverage_scope: z.string().min(1), count_semantics: z.string().min(1), filters: z.object({ country_code: z.string().nullable().optional(), region: z.string().nullable().optional(), category: z.string().nullable().optional(), source_type: z.string().nullable().optional(), display_precision: z.string().nullable().optional(), lifecycle_status: z.string().nullable().optional() }) }), dimensions: z.record(z.string(), z.array(facet)) });
export type Facet = Readonly<{ value: string; count: number }>;
export type FacetResponse = Readonly<{ profile: LocalProfile; releaseId: string; ruleset: string; coverageScope: string; countSemantics: string; dimensions: Readonly<Record<string, readonly Facet[]>> }>;
const fail = (kind: ApiError['kind'], message: string): ApiError => Object.assign(new Error(message), { kind });
export type FacetFilters = Readonly<{ country_code?: string | undefined; region?: string | undefined; category?: string | undefined; source_type?: string | undefined; display_precision?: string | undefined; lifecycle_status?: string | undefined }>;

const normalizedFilter = (value: string | null | undefined): string | null => {
  const normalized = value?.trim();
  return normalized ? normalized : null;
};

export class FacetsRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, private readonly baseUrl = '') {}
  async get(profile: LocalProfile, filters: FacetFilters, expected: { releaseId: string; ruleset: string }, signal?: AbortSignal): Promise<FacetResponse> {
    const params = new URLSearchParams({ profile });
    for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
    let response: Response;
    try { const init: RequestInit = { cache: 'no-store' }; if (signal) init.signal = signal; response = await this.fetcher.call(globalThis, `${this.baseUrl}/api/v2/discovery/facets?${params}`, init); }
    catch (error) { if (error instanceof DOMException && error.name === 'AbortError') throw fail('aborted', 'Facet request was aborted.'); throw fail('network', 'Coverage summary could not connect to the V2 service.'); }
    if (!response.ok) throw fail(response.status >= 500 ? 'unavailable' : response.status === 429 ? 'rate-limited' : 'http', `Coverage summary request failed with status ${response.status}.`);
    let payload: unknown;
    try { payload = await response.json(); } catch { throw fail('invalid-contract', 'Coverage summary response was not valid JSON.'); }
    const parsed = responseSchema.safeParse(payload);
    if (!parsed.success) throw fail('invalid-contract', 'Coverage summary response was rejected safely.');
    if (parsed.data.meta.profile !== profile || parsed.data.meta.release_id !== expected.releaseId || parsed.data.meta.ruleset_version !== expected.ruleset) throw fail('invalid-contract', 'Coverage summary belongs to a different profile or promoted release.');
    const responseFilters = parsed.data.meta.filters;
    for (const key of ['country_code', 'region', 'category', 'source_type', 'display_precision', 'lifecycle_status'] as const) {
      if (normalizedFilter(filters[key]) !== normalizedFilter(responseFilters[key])) throw fail('invalid-contract', 'Coverage summary belongs to a different filter scope.');
    }
    return { profile, releaseId: parsed.data.meta.release_id, ruleset: parsed.data.meta.ruleset_version, coverageScope: parsed.data.meta.coverage_scope, countSemantics: parsed.data.meta.count_semantics, dimensions: parsed.data.dimensions };
  }
}
