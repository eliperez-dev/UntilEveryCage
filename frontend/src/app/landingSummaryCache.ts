import { z } from 'zod';
import type { PublicReleaseIdentity } from '../api/PublicReleaseRepository';
import type { LandingReleaseSummary } from './landingReleaseSummary';

export const LANDING_SUMMARY_CACHE_KEY = 'uec.landing-release-summary.v1';
export const LANDING_SUMMARY_CACHE_TTL_MS = 24 * 60 * 60 * 1000;
export type LandingSummaryStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export type LandingSummaryCacheOptions = Readonly<{ storage?: LandingSummaryStorage | null; now?: () => number }>;
const count = z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER);
const entrySchema = z.object({
  version: z.literal(1), profile: z.literal('official'), savedAt: count,
  identity: z.object({ releaseId: z.string().min(1).max(160), manifestSha256: z.string().regex(/^[a-f0-9]{64}$/), suppressionGeneration: count }).strict(),
  summary: z.object({ releaseId: z.string().min(1).max(160), records: count, mapped: count, sources: count, countries: count }).strict(),
}).strict().refine(entry => entry.identity.releaseId === entry.summary.releaseId
  && entry.summary.mapped <= entry.summary.records && entry.summary.sources <= entry.summary.records
  && entry.summary.countries <= entry.summary.mapped
  && (entry.summary.records === 0) === (entry.summary.sources === 0)
  && (entry.summary.mapped === 0) === (entry.summary.countries === 0));
export type LandingSummaryCacheEntry = z.infer<typeof entrySchema>;

export function landingSummaryStorage(): LandingSummaryStorage | null {
  try { return globalThis.localStorage ?? null; } catch { return null; }
}
export function clearLandingSummaryCache(storage: LandingSummaryStorage | null): void {
  try { storage?.removeItem(LANDING_SUMMARY_CACHE_KEY); } catch { /* Storage is optional. */ }
}
export function readLandingSummaryCache(storage: LandingSummaryStorage | null, now: number): LandingSummaryCacheEntry | null {
  try {
    const raw = storage?.getItem(LANDING_SUMMARY_CACHE_KEY);
    if (raw === null || raw === undefined) return null;
    if (raw.length > 2048) throw new Error('Oversized aggregate cache');
    const parsed = entrySchema.safeParse(JSON.parse(raw));
    if (!parsed.success || !Number.isSafeInteger(now) || parsed.data.savedAt > now
      || now - parsed.data.savedAt >= LANDING_SUMMARY_CACHE_TTL_MS) throw new Error('Invalid aggregate cache');
    return parsed.data;
  } catch { clearLandingSummaryCache(storage); return null; }
}
export function landingSummaryIdentityMatches(identity: PublicReleaseIdentity, cached: LandingSummaryCacheEntry): boolean {
  return identity.releaseId === cached.identity.releaseId && identity.manifestSha256 === cached.identity.manifestSha256
    && identity.suppressionGeneration === cached.identity.suppressionGeneration;
}
/** Call only after fresh before/after manifest checks. No partial totals or rows. */
export function writeLandingSummaryCache(storage: LandingSummaryStorage | null, identity: PublicReleaseIdentity, summary: LandingReleaseSummary, now: number): void {
  const parsed = entrySchema.safeParse({ version: 1, profile: 'official', savedAt: now,
    identity: { releaseId: identity.releaseId, manifestSha256: identity.manifestSha256, suppressionGeneration: identity.suppressionGeneration }, summary });
  if (!parsed.success) return;
  try { storage?.setItem(LANDING_SUMMARY_CACHE_KEY, JSON.stringify(parsed.data)); } catch { /* Quota/private mode must not block live totals. */ }
}
