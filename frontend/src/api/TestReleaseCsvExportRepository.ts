import type { FetchLike } from './LocalLocationRepository';
import { DEV_PREVIEW_TOKEN_HEADER, TEST_RELEASE_PATH, TEST_RELEASE_LABEL } from '../features/devPreview/devPreviewContract';
export type TestReleaseCsv = Readonly<{ body: string; releaseId: string; profile: string; label: string }>;
export class TestReleaseCsvExportRepository {
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, private readonly baseUrl = '') {}
  async download(profile: string, token: string): Promise<TestReleaseCsv> { const response = await this.fetcher.call(globalThis, `${this.baseUrl}${TEST_RELEASE_PATH}/locations.csv?profile=${encodeURIComponent(profile)}`, { cache: 'no-store', headers: { [DEV_PREVIEW_TOKEN_HEADER]: token } }); if (!response.ok) throw new Error(`Private test-release CSV unavailable (HTTP ${response.status}).`); if (response.headers.get('x-uec-test-release') !== 'true') throw new Error('Private test-release CSV marker was missing.'); const body = await response.text(); const releaseId = response.headers.get('x-uec-release-id'); if (!releaseId || !body.trim()) throw new Error('Private test-release CSV did not include release context.'); return { body, releaseId, profile, label: TEST_RELEASE_LABEL }; }
}
