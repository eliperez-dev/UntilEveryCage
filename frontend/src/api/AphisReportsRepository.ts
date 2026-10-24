import { aphisReportLinksEnvelopeSchema, type PublicAphisReportLink } from './publicGraphSchema';
import type { LocalProfile } from './LocalLocationRepository';
import type { LocationSourceFacts } from '../domain/location';

export type AphisReportKind = 'annual_reports' | 'inspections';
export type AphisReportPage = Readonly<{
  data: readonly PublicAphisReportLink[];
  releaseId: string;
  ruleset: string;
  profile: LocalProfile;
  nextCursor: string | null;
}>;

export function isAphisRelevant(sourceId?: string, sourceFacts?: LocationSourceFacts): boolean {
  return sourceId === 'us.aphis' || sourceId === 'us.aphis.annual-reports' || sourceId === 'us.inspections'
    || Boolean(sourceFacts?.aphisAnnualReports?.length || sourceFacts?.aphisDatedInspections?.length);
}

export class AphisReportsRepository {
  constructor(private readonly fetcher: typeof fetch = globalThis.fetch) {}

  async page(
    facilityId: string,
    profile: LocalProfile,
    kind: AphisReportKind,
    releaseId: string,
    limit = 20,
    cursor?: string,
    signal?: AbortSignal,
  ): Promise<AphisReportPage> {
    const params = new URLSearchParams({ profile, release_id: releaseId, kind, limit: String(limit) });
    if (cursor) params.set('cursor', cursor);
    const response = await this.fetcher(`/api/v2/locations/${encodeURIComponent(facilityId)}/aphis-report-links?${params}`, {
      cache: 'no-store', ...(signal ? { signal } : {}),
    });
    if (!response.ok) throw new Error('APHIS report references are unavailable.');
    let body: unknown;
    try { body = await response.json(); } catch { throw new Error('APHIS report response was not valid JSON.'); }
    const parsed = aphisReportLinksEnvelopeSchema.safeParse(body);
    if (!parsed.success || parsed.data.meta.release_id !== releaseId || parsed.data.meta.kind !== kind || parsed.data.meta.profile !== profile) {
      throw new Error('APHIS report response did not match the selected release.');
    }
    return {
      data: parsed.data.data, releaseId: parsed.data.meta.release_id,
      ruleset: parsed.data.meta.ruleset_version, profile, nextCursor: parsed.data.meta.next_cursor,
    };
  }
}
