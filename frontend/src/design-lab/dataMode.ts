export type DesignLabDataMode = 'synthetic' | 'real-preview';

export function selectDesignLabDataMode(isDevelopment: boolean, serverMode: string | null): DesignLabDataMode {
  return isDevelopment && serverMode === 'real-preview' ? 'real-preview' : 'synthetic';
}
