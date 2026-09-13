import { describe, expect, it, vi } from 'vitest';
import { LocalCsvExportRepository } from '../../src/api/LocalCsvExportRepository';

const response = (status = 200, body = 'facility_id\nabc\n') => new Response(body, { status, headers: { 'x-uec-release-id': 'release-1', 'x-uec-manifest-sha256': 'digest-1' } });

describe('LocalCsvExportRepository', () => {
  it('returns bounded CSV and release manifest context', async () => {
    const result = await new LocalCsvExportRepository(vi.fn().mockResolvedValue(response())).download('official');
    expect(result).toMatchObject({ releaseId: 'release-1', profile: 'official', manifestSha256: 'digest-1' });
  });
  it.each([400, 404, 429, 503])('surfaces HTTP status %s', async (status) => {
    await expect(new LocalCsvExportRepository(vi.fn().mockResolvedValue(response(status))).download('official')).rejects.toMatchObject({ status });
  });
  it('rejects an empty response or missing release context', async () => {
    await expect(new LocalCsvExportRepository(vi.fn().mockResolvedValue(response(200, ''))).download('official')).rejects.toThrow(/eligible release context/);
  });
});
