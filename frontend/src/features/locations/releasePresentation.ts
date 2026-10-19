const LEGACY_RELEASE_LABELS: Readonly<Record<string, string>> = Object.freeze({
  'v0-candidate-2026-10-04-r3': 'v0: Early Access',
});

/** Public labels never expose immutable release identifiers. */
export function publicReleaseLabel(releaseId: string | null | undefined, manifestLabel?: string | null): string | null {
  if (!releaseId) return null;
  if (LEGACY_RELEASE_LABELS[releaseId]) return LEGACY_RELEASE_LABELS[releaseId];
  if (manifestLabel && /^\d{4}-\d{2}-\d{2}$/.test(manifestLabel)) return manifestLabel;
  const date = /^release-(\d{4}-\d{2}-\d{2})$/.exec(releaseId)?.[1];
  return date ?? 'Public release';
}
