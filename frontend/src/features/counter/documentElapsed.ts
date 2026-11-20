import { readable } from 'svelte/store';

/** One document clock, shared across mounted counters and SPA route changes. */
export const documentElapsedMilliseconds = readable(0, set => {
  if (typeof window === 'undefined') return;
  let timer: number | undefined;
  const update = () => set(Math.max(0, performance.now()));
  const stop = () => { if (timer !== undefined) window.clearInterval(timer); timer = undefined; };
  const sync = () => {
    stop();
    if (document.hidden) return;
    update();
    timer = window.setInterval(update, 1000);
  };
  document.addEventListener('visibilitychange', sync);
  sync();
  return () => {
    stop();
    document.removeEventListener('visibilitychange', sync);
  };
});

export function estimateSinceDocumentOpen(rate: number, elapsedMilliseconds: number) {
  if (!Number.isFinite(rate) || rate <= 0 || !Number.isFinite(elapsedMilliseconds) || elapsedMilliseconds <= 0) return 0;
  return Math.floor(rate * elapsedMilliseconds / 1000);
}
