import type { FetchLike } from './LocalLocationRepository';

export type CsvExport = Readonly<{
  body: string;
  releaseId: string;
  profile: string;
  manifestSha256?: string;
}>;

export class LocalCsvExportRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, private readonly baseUrl = '') {}

  async download(profile: 'official' | 'secondary' | 'community' = 'official'): Promise<CsvExport> {
    const response = await this.fetcher.call(globalThis, `${this.baseUrl}/api/v2/locations.csv?profile=${profile}`, { cache: 'no-store' });
    if (!response.ok) {
      let message = `Local V2 export request failed with status ${response.status}.`;
      try {
        const payload = await response.json() as { error?: { message?: string } };
        if (payload.error?.message) message = payload.error.message;
      } catch { /* Preserve the status-based safe message. */ }
      throw Object.assign(new Error(message), { status: response.status });
    }
    const body = await response.text();
    const releaseId = response.headers.get('x-uec-release-id');
    const responseProfile = profile;
    if (!releaseId || !body.trim()) throw new Error('The local V2 export did not include eligible release context.');
    const manifestSha256 = response.headers.get('x-uec-manifest-sha256');
    return manifestSha256 ? { body, releaseId, profile: responseProfile, manifestSha256 } : { body, releaseId, profile: responseProfile };
  }
}
