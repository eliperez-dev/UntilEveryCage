/** Retry bounded server admission once, unless the visitor has moved on. */
export async function retrySearchBusy<T>(request: () => Promise<T>, signal: AbortSignal): Promise<T> {
  signal.throwIfAborted();
  try {
    return await request();
  } catch (error) {
    if (!error || typeof error !== 'object' || !('code' in error) || error.code !== 'search_busy') throw error;
    signal.throwIfAborted();
    await new Promise<void>(resolve => {
      const timer = setTimeout(finish, 1_000);
      signal.addEventListener('abort', finish, { once: true });
      function finish() {
        clearTimeout(timer);
        signal.removeEventListener('abort', finish);
        resolve();
      }
    });
    signal.throwIfAborted();
    return request();
  }
}
