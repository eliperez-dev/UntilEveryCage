export type DesignLabDataMode = 'synthetic' | 'real-preview' | 'public-release';

export function selectDesignLabDataMode(isDevelopment: boolean, serverMode: string | null, privatePreview = false): DesignLabDataMode {
  if (!isDevelopment) return 'public-release';
  if (!privatePreview) return 'public-release';
  return serverMode === 'real-preview' ? 'real-preview' : 'synthetic';
}
