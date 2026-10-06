export type DesignLabDataMode = 'synthetic' | 'real-preview' | 'public-release';

export function selectDesignLabDataMode(isDevelopment: boolean, serverMode: string | null, privatePreview = false): DesignLabDataMode {
  if (!isDevelopment) return 'public-release';
  if (!privatePreview) return 'public-release';
  return serverMode === 'real-preview' ? 'real-preview' : 'synthetic';
}

/** Public record lists wait for the release identity; identical startup observers share one request key. */
export function shouldScheduleListLoad(mode: DesignLabDataMode, releaseId: string | null, observedKey: string | undefined, nextKey: string): boolean {
  return mode !== 'synthetic' && (mode !== 'public-release' || releaseId !== null) && observedKey !== nextKey;
}
