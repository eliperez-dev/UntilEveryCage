import { z } from 'zod';
import type { LocalProfile } from './LocalLocationRepository';
const manifestEnvelope = z.object({ api_version: z.literal('v2'), data: z.object({ release_id: z.string().min(1).max(160), profile: z.enum(['official','secondary','community']), manifest: z.record(z.unknown()), manifest_sha256: z.string().regex(/^[a-f0-9]{64}$/), suppression_generation: z.number().int().nonnegative() }).strict() }).strict();
export class PublicReleaseError extends Error {}
/** Public availability does not depend on whether a release has map tiles. */
export class PublicReleaseRepository {
  constructor(private readonly fetcher: typeof fetch = globalThis.fetch) {}
  async current(profile: LocalProfile, signal?: AbortSignal): Promise<{ releaseId: string } | null> {
    const response = await this.fetcher.call(globalThis, `/api/v2/releases/manifest?profile=${profile}`, { method:'GET', cache:'no-store', credentials:'omit', headers:{Accept:'application/json'}, ...(signal ? {signal} : {}) });
    if (response.status === 404) return null;
    if (!response.ok) throw new PublicReleaseError('Release availability could not be checked. Try again.');
    const parsed = manifestEnvelope.safeParse(await response.json());
    if (!parsed.success || parsed.data.data.profile !== profile) throw new PublicReleaseError('Release availability could not be checked. Try again.');
    return {releaseId:parsed.data.data.release_id};
  }
}
