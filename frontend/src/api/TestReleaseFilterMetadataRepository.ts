import { z } from 'zod';
import type { FetchLike } from './LocalLocationRepository';
import { DEV_PREVIEW_TOKEN_HEADER, TEST_RELEASE_API_VERSION, TEST_RELEASE_PATH } from '../features/devPreview/devPreviewContract';

const dimension = z.array(z.object({ value: z.string(), count: z.number().int().nonnegative() }));
const schema = z.object({ data: z.null(), meta: z.object({ api_version: z.literal(TEST_RELEASE_API_VERSION), environment: z.literal('test-only'), test_only: z.literal(true), private_preview: z.literal(true), release_status: z.literal('candidate'), release_id: z.string(), profile: z.enum(['official', 'secondary', 'community']), coverage_scope: z.string(), count_semantics: z.string(), preview_label: z.string(), result_count: z.number().int().nonnegative() }), dimensions: z.object({ country_code: dimension, category: dimension, display_precision: dimension, source_type: dimension }) });
export type TestReleaseFilterMetadata = z.infer<typeof schema>;
export class TestReleaseFilterMetadataRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, private readonly baseUrl = '') {}
  async get(profile: string, token: string): Promise<TestReleaseFilterMetadata> { const response = await this.fetcher.call(globalThis, `${this.baseUrl}${TEST_RELEASE_PATH}/discovery/facets?profile=${encodeURIComponent(profile)}`, { cache: 'no-store', headers: { [DEV_PREVIEW_TOKEN_HEADER]: token } }); if (!response.ok) throw new Error(`Private test-release facets unavailable (HTTP ${response.status}).`); const result = schema.safeParse(await response.json()); if (!result.success) throw new Error('Private test-release facets were rejected safely.'); return result.data; }
}
