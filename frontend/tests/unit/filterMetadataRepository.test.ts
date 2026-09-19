import { describe, expect, it, vi } from 'vitest';
import { FilterMetadataRepository } from '../../src/api/FilterMetadataRepository';

const valid = { api_version: 'v2', contract_version: 'v1', dimensions: { country_code: { values: ['DK'] }, category: { values: ['dairy'] }, source_type: { values: ['official'] }, profile: { values: ['official'], default: 'official' }, display_precision: { values: ['city'] }, lifecycle_status: { values: ['active_observed'] } }, pagination: { limit_max: 1000, cursor: 'facility_id' }, privacy: 'eligible only' };
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe('FilterMetadataRepository', () => {
  it('accepts the versioned allowlisted dimensions', async () => { await expect(new FilterMetadataRepository(vi.fn().mockResolvedValue(response(valid))).get()).resolves.toMatchObject({ dimensions: { category: { values: ['dairy'] } } }); });
  it('rejects malformed and unavailable metadata safely', async () => { await expect(new FilterMetadataRepository(vi.fn().mockResolvedValue(response({ api_version: 'v1' }))).get()).rejects.toThrow(/rejected safely/); await expect(new FilterMetadataRepository(vi.fn().mockResolvedValue(response({}, 503))).get()).rejects.toThrow(/503/); });
});
