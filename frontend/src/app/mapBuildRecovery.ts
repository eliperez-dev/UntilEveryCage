const recoveryKey = 'uec-map-build-recovery';
let checking = false;

/** A restored document may reference an asset removed during a deployment. */
export async function recoverMapBuild(isCurrent: () => boolean): Promise<boolean> {
  if (checking) return false;
  const current = document.querySelector<HTMLScriptElement>('script[type="module"][src]')?.src;
  if (!current || !isCurrent()) return false;
  checking = true;
  try {
    const response = await fetch(window.location.pathname + window.location.search, {
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
      headers: { Accept: 'text/html' },
    });
    if (!response.ok || !response.headers.get('content-type')?.includes('text/html')) return false;
    const html = new DOMParser().parseFromString(await response.text(), 'text/html');
    const source = html.querySelector<HTMLScriptElement>('script[type="module"][src]')?.getAttribute('src');
    if (!source || !isCurrent()) return false;
    const latest = new URL(source, window.location.href);
    if (latest.origin !== window.location.origin || latest.href === current
      || sessionStorage.getItem(recoveryKey)) return false;
    sessionStorage.setItem(recoveryKey, latest.href);
    window.location.reload();
    return true;
  } catch {
    return false;
  } finally {
    checking = false;
  }
}

export function clearMapBuildRecovery(): void {
  try { sessionStorage.removeItem(recoveryKey); } catch { /* Storage may be unavailable. */ }
}
