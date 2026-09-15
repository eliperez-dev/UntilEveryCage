import { z } from 'zod';
import type { FetchLike } from './LocalLocationRepository';

const dimension = z.object({ values: z.array(z.string()), default: z.string().optional() });
const metadataSchema = z.object({ api_version: z.literal('v2'), contract_version: z.string(), dimensions: z.object({ country_code: dimension, region: dimension.optional(), category: dimension, source_type: dimension, profile: dimension, display_precision: dimension, lifecycle_status: dimension }), spatial: z.object({ bbox: z.array(z.string()), radius: z.array(z.string()) }).optional(), search: z.object({ parameter: z.string(), fields: z.array(z.string()) }).optional(), pagination: z.object({ limit_max: z.number().int().positive(), cursor: z.string() }), privacy: z.string().min(1) });
export type FilterMetadata = z.infer<typeof metadataSchema>;
export class FilterMetadataRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, private readonly baseUrl = '') {}
  async get(): Promise<FilterMetadata> { const response = await this.fetcher.call(globalThis, `${this.baseUrl}/api/v2/discovery/filters`, { cache: 'no-store' }); if (!response.ok) throw Object.assign(new Error(`Filter metadata unavailable (${response.status}).`), { status: response.status }); const result = metadataSchema.safeParse(await response.json()); if (!result.success) throw new Error('Filter metadata was rejected safely.'); return result.data; }
}
