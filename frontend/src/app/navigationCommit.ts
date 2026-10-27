/** Keep a lazy workspace from replacing a header link during its native click. */
export function createNavigationCommitGuard(host: Window) {
  let pressed = false, disposed = false;
  let pointerId: number | undefined;
  let pending: (() => void) | undefined;
  let releaseTimer: ReturnType<typeof setTimeout> | undefined;
  const down = (event: PointerEvent) => {
    if (event.button !== 0 || !(event.target instanceof Element) || !event.target.closest('.masthead a[href]')) return;
    clearTimeout(releaseTimer); releaseTimer = undefined;
    pressed = true; pointerId = event.pointerId;
  };
  const release = (event?: PointerEvent) => {
    if (!pressed || (event && event.pointerId !== pointerId)) return;
    clearTimeout(releaseTimer);
    // Native click/default navigation follows pointerup. A task boundary keeps
    // the original anchor attached until that navigation has had its turn.
    releaseTimer = setTimeout(() => {
      releaseTimer = undefined; pressed = false; pointerId = undefined;
      const commit = pending; pending = undefined;
      if (!disposed) commit?.();
    }, 0);
  };
  const blur = () => release();
  host.addEventListener('pointerdown', down, true);
  host.addEventListener('pointerup', release, true);
  host.addEventListener('pointercancel', release, true);
  host.addEventListener('blur', blur);
  return {
    commit(callback: () => void) { if (!disposed) { if (pressed) pending = callback; else callback(); } },
    dispose() {
      disposed = true; clearTimeout(releaseTimer); pending = undefined;
      host.removeEventListener('pointerdown', down, true);
      host.removeEventListener('pointerup', release, true);
      host.removeEventListener('pointercancel', release, true);
      host.removeEventListener('blur', blur);
    },
  };
}
