import { z } from 'zod';
import { locationSchema, type WireLocation } from './wireSchema';
import { mapWireLocation, type FetchLike, type LocalListResult, type LocalProfile } from './LocalLocationRepository';
import { TEST_RELEASE_API_VERSION, TEST_RELEASE_LABEL, TEST_RELEASE_PATH, DEV_PREVIEW_TOKEN_HEADER } from '../features/devPreview/devPreviewContract';

const envelope = z.object({ data: z.array(locationSchema), meta: z.object({ api_version: z.literal(TEST_RELEASE_API_VERSION), environment: z.literal('test-only'), test_only: z.literal(true), private_preview: z.literal(true), release_status: z.literal('candidate'), release_id: z.string(), profile: z.enum(['official', 'secondary', 'community']), coverage_scope: z.string(), count_semantics: z.string(), preview_label: z.string(), result_count: z.number().int().nonnegative(), next_cursor: z.string().nullable().optional() }) });
export class TestReleaseRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, private readonly baseUrl = '') {}
  async list(profile: LocalProfile = 'official', token = '', signal?: AbortSignal): Promise<LocalListResult> {
    const init: RequestInit = { cache: 'no-store', headers: { [DEV_PREVIEW_TOKEN_HEADER]: token } }; if (signal) init.signal = signal;
    const response = await this.fetcher.call(globalThis, `${this.baseUrl}${TEST_RELEASE_PATH}/locations?profile=${profile}&limit=100`, init);
    if (!response.ok) throw new Error(`Private test release unavailable (HTTP ${response.status}).`);
    const parsed = envelope.safeParse(await response.json()); if (!parsed.success) throw new Error('Private test release response was rejected safely.');
    return { locations: parsed.data.data.map(mapWireLocation), releaseId: parsed.data.meta.release_id, profile, coverageNote: `${TEST_RELEASE_LABEL}. ${parsed.data.meta.coverage_scope}.`, coverageScope: parsed.data.meta.coverage_scope, countSemantics: parsed.data.meta.count_semantics, nextCursor: parsed.data.meta.next_cursor ?? null };
  }
}
