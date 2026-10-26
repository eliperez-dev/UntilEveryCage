import { z } from 'zod';
import type { FetchLike, LocationFilters } from './LocalLocationRepository';
import type { PublicReleaseIdentity } from './PublicReleaseRepository';

const responseSchema = z.object({
  api_version: z.literal('v2'),
  data: z.object({ facility_ids: z.array(z.string().uuid()) }).strict(),
  meta: z.object({ profile: z.literal('official'), release_id: z.string(), manifest_sha256: z.string().regex(/^[a-f0-9]{64}$/), suppression_generation: z.number().int().nonnegative(), total_count: z.number().int().nonnegative(), mapped_count: z.number().int().nonnegative() }).strict(),
}).strict();
export class PublicMapMatchesError extends Error {
  constructor(message = 'Matching map locations could not be loaded. Try again.') { super(message); this.name = 'PublicMapMatchesError'; }
}
export type PublicMapMatches = Readonly<{ facilityIds: readonly string[]; totalCount: number; mappedCount: number }>;

/** A transient, no-store result, never keyed or persisted by a visitor's search. */
export class PublicMapMatchesRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch) {}
  async get(filters: LocationFilters, expected: PublicReleaseIdentity, signal?: AbortSignal): Promise<PublicMapMatches> {
    const params = new URLSearchParams({ profile: 'official', release_id: expected.releaseId });
    for (const [key, value] of Object.entries(filters)) {
      if (['cursor', 'offset', 'limit'].includes(key) || value === undefined || value === '') continue;
      if (key === 'category_keys') { if (Array.isArray(value) && value.length) params.set(key, [...new Set(value)].join(',')); }
      else params.set(key, String(value));
    }
    let response: Response;
    try {
      response = await this.fetcher.call(globalThis, `/api/v2/map/matches?${params}`, { method: 'GET', cache: 'no-store', credentials: 'omit', headers: { Accept: 'application/json' }, ...(signal ? { signal } : {}) });
    } catch (error) {
      if (signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')) throw error;
      throw new PublicMapMatchesError();
    }
    if (!response.ok) throw new PublicMapMatchesError();
    let raw: unknown;
    try { raw = await response.json(); } catch { throw new PublicMapMatchesError(); }
    const parsed = responseSchema.safeParse(raw);
    if (!parsed.success) throw new PublicMapMatchesError('Matching map locations returned an invalid response. Try again.');
    const { data, meta } = parsed.data;
    if (meta.release_id !== expected.releaseId || meta.manifest_sha256 !== expected.manifestSha256 || meta.suppression_generation !== expected.suppressionGeneration || meta.mapped_count !== data.facility_ids.length || new Set(data.facility_ids).size !== data.facility_ids.length || meta.mapped_count > meta.total_count) throw new PublicMapMatchesError('Matching map locations belong to a different release. Try again.');
    return { facilityIds: data.facility_ids, totalCount: meta.total_count, mappedCount: meta.mapped_count };
  }
}
