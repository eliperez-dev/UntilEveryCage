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
  it('requests the selected non-official profile and requires CSV content', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(200, 'facility_id\nsecondary-1\n'));
    await expect(new LocalCsvExportRepository(fetcher).download('secondary')).resolves.toMatchObject({ profile: 'secondary' });
    expect(String(fetcher.mock.calls[0]?.[0])).toContain('profile=secondary');
    await expect(new LocalCsvExportRepository(vi.fn().mockResolvedValue(new Response('{}', { status: 200, headers: { 'x-uec-release-id': 'release-1', 'content-type': 'application/json' } }))).download('official')).rejects.toMatchObject({ kind: 'invalid-contract' });
  });
  it('rejects a non-loopback API origin before sending an export request', () => {
    expect(() => new LocalCsvExportRepository(vi.fn(), 'https://external.example')).toThrow('Local API origin must be loopback HTTP.');
  });
});
