import { describe, expect, it, vi } from 'vitest';
import { AphisReportsRepository, isAphisRelevant } from '../../src/api/AphisReportsRepository';

const annual = {
  reference_id: '550e8400-e29b-41d4-a716-446655440001', source_id: 'us.aphis.annual-reports',
  evidence_type: 'annual_reports', event_date: null, event_period: '2025', observed_at: '2026-01-01T00:00:00Z',
  source_url: 'https://direct.aphis.usda.gov/awa/research-facility-report/annual-summary', match_method: 'exact_source_identifier',
  report_url: 'https://aphis.my.site.com/PublicSearchTool/s/annual-report?id=public-report', column_e_url: null,
};
const inspection = {
  ...annual, reference_id: '550e8400-e29b-41d4-a716-446655440002', source_id: 'us.inspections',
  evidence_type: 'inspections', event_date: '2025-02-03', event_period: null,
  source_url: 'https://direct.aphis.usda.gov/awa/search/inspection-reports', report_url: null,
};
const envelope = (data: readonly unknown[], nextCursor: string | null = null, kind: 'annual_reports' | 'inspections' = 'annual_reports') => ({
  api_version: 'v2', data, meta: {
    profile: 'official', release_id: 'release-1', ruleset_version: 'rules', kind, limit: 20,
    next_cursor: nextCursor, public_projection: true,
  },
});
const entity = '550e8400-e29b-41d4-a716-446655440000';

describe('APHIS report link repository', () => {
  it('returns only a selected release report kind and actual document links', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope([annual], null)), { status: 200 }));
    const repository = new AphisReportsRepository(fetcher);
    await expect(repository.page(entity, 'official', 'annual_reports', 'release-1')).resolves.toMatchObject({
      data: [annual], releaseId: 'release-1', nextCursor: null,
    });
    expect(String(fetcher.mock.calls[0]?.[0])).toContain('/api/v2/locations/' + entity + '/aphis-report-links?profile=official&release_id=release-1&kind=annual_reports&limit=20');
  });

  it('preserves an empty filtered page cursor for continuation', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope([], '550e8400-e29b-41d4-a716-446655440010')), { status: 200 }));
    const page = await new AphisReportsRepository(fetcher).page(entity, 'official', 'annual_reports', 'release-1');
    expect(page).toMatchObject({ data: [], nextCursor: '550e8400-e29b-41d4-a716-446655440010' });
  });

  it('passes the cursor when loading the next page', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope([annual], null)), { status: 200 }));
    await new AphisReportsRepository(fetcher).page(entity, 'official', 'annual_reports', 'release-1', 20, '550e8400-e29b-41d4-a716-446655440010');
    expect(String(fetcher.mock.calls[0]?.[0])).toContain('cursor=550e8400-e29b-41d4-a716-446655440010');
  });

  it('rejects a report row from another kind or release', async () => {
    const wrongKind = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope([inspection])), { status: 200 }));
    await expect(new AphisReportsRepository(wrongKind).page(entity, 'official', 'annual_reports', 'release-1')).rejects.toThrow('APHIS report response did not match');
    const wrongRelease = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope([annual], null)), { status: 200 }));
    await expect(new AphisReportsRepository(wrongRelease).page(entity, 'official', 'annual_reports', 'release-2')).rejects.toThrow('APHIS report response did not match');
    const wrongHost = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope([{ ...annual, report_url: 'https://example.test/phishing' }])), { status: 200 }));
    await expect(new AphisReportsRepository(wrongHost).page(entity, 'official', 'annual_reports', 'release-1')).rejects.toThrow('APHIS report response did not match');
  });

  it('accepts APHIS Salesforce document links only on the exact distribution route and query shape', async () => {
    const officialDocument = {
      ...annual,
      report_url: 'https://aphis.file.force.com/sfc/dist/version/download/?oid=00D000000000000&ids=068000000000000AAA&d=token/with-safe~chars&asPdf=true',
    };
    const accepted = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope([officialDocument])), { status: 200 }));
    await expect(new AphisReportsRepository(accepted).page(entity, 'official', 'annual_reports', 'release-1'))
      .resolves.toMatchObject({ data: [officialDocument] });
    const unrelated = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope([{
      ...officialDocument,
      report_url: 'https://example.force.com/sfc/dist/version/download/?oid=00D000000000000&ids=068000000000000AAA&d=token&asPdf=true',
    }])), { status: 200 }));
    await expect(new AphisReportsRepository(unrelated).page(entity, 'official', 'annual_reports', 'release-1'))
      .rejects.toThrow('APHIS report response did not match');
    const wrongQueryShape = vi.fn().mockResolvedValue(new Response(JSON.stringify(envelope([{
      ...officialDocument,
      report_url: 'https://aphis.file.force.com/sfc/dist/version/download/?oid=00D000000000000&ids=068000000000000AAA&d=token&asPdf=true&redirect=https://evil.example',
    }])), { status: 200 }));
    await expect(new AphisReportsRepository(wrongQueryShape).page(entity, 'official', 'annual_reports', 'release-1'))
      .rejects.toThrow('APHIS report response did not match');
  });

  it('provides empty state data and lets callers retry an upstream failure', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(envelope([])), { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 502 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(envelope([annual])), { status: 200 }));
    const repository = new AphisReportsRepository(fetcher);
    const args = [entity, 'official', 'annual_reports', 'release-1'] as const;
    await expect(repository.page(...args)).resolves.toMatchObject({ data: [] });
    await expect(repository.page(...args)).rejects.toThrow('APHIS report references are unavailable');
    await expect(repository.page(...args)).resolves.toMatchObject({ data: [annual] });
  });

  it.each<[string | undefined, Parameters<typeof isAphisRelevant>[1], boolean]>([
    ['us.aphis', undefined, true], ['us.aphis.annual-reports', undefined, true], ['us.inspections', undefined, true],
    ['us.fsis', undefined, false], [undefined, { aphisAnnualReports: [] }, false],
    [undefined, { aphisDatedInspections: [{ inspectionDate: '2025-01-01', sourceUrl: 'https://example.test', safeProvenance: { sourceId: 'us.inspections', evidenceType: 'inspections', matchMethod: 'exact_source_identifier', matchedIdentifierTypes: ['certificate_number'] } }] }, true],
  ])('relevance for %s is %s', (sourceId, facts, expected) => {
    expect(isAphisRelevant(sourceId, facts)).toBe(expected);
  });
});
