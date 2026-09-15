import type { FetchLike, LocalProfile } from './LocalLocationRepository';
import type { ApiError } from './errors';

export type CsvExport = Readonly<{
  body: string;
  releaseId: string;
  profile: string;
  manifestSha256?: string;
}>;

export class LocalCsvExportRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, private readonly baseUrl = '') {}

  async download(profile: LocalProfile = 'official', signal?: AbortSignal): Promise<CsvExport> {
    const init: RequestInit = { cache: 'no-store' }; if (signal) init.signal = signal;
    const response = await this.fetcher.call(globalThis, `${this.baseUrl}/api/v2/locations.csv?profile=${profile}`, init);
    if (!response.ok) {
      let message = `Local V2 export request failed with status ${response.status}.`;
      let code: string | undefined;
      try {
        const payload = await response.json() as { error?: { code?: string; message?: string } };
        code = payload.error?.code;
        if (payload.error?.message) message = payload.error.message;
      } catch { /* Preserve the status-based safe message. */ }
      const kind: ApiError['kind'] = response.status === 404 ? 'no-release' : response.status === 429 ? 'rate-limited' : response.status >= 500 ? 'unavailable' : 'http';
      throw Object.assign(new Error(message), { kind, status: response.status, code });
    }
    const contentType = response.headers.get('content-type');
    if (contentType?.toLowerCase().includes('application/json')) throw Object.assign(new Error('The local V2 export response was not CSV.'), { kind: 'invalid-contract' as const });
    const body = await response.text();
    const releaseId = response.headers.get('x-uec-release-id');
    const responseProfile = profile;
    if (!releaseId || !body.trim()) throw new Error('The local V2 export did not include eligible release context.');
    const manifestSha256 = response.headers.get('x-uec-manifest-sha256');
    return manifestSha256 ? { body, releaseId, profile: responseProfile, manifestSha256 } : { body, releaseId, profile: responseProfile };
  }
}
