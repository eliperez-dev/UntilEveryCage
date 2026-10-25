export interface ApplicationVersion {
  version: string;
}

export function parseApplicationVersion(value: unknown): ApplicationVersion | null {
  if (!value || typeof value !== 'object') return null;
  const version = (value as { application_version?: unknown }).application_version;
  return typeof version === 'string' && /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(version)
    ? { version }
    : null;
}

export function createApplicationVersionRepository(fetcher: typeof fetch = globalThis.fetch) {
  let pending: Promise<ApplicationVersion | null> | undefined;
  return {
    current(): Promise<ApplicationVersion | null> {
      if (!pending) {
        pending = fetcher('/health/live', { headers: { Accept: 'application/json' } })
          .then(async response => response.ok ? parseApplicationVersion(await response.json()) : null)
          .catch(() => null);
      }
      return pending;
    },
  };
}
