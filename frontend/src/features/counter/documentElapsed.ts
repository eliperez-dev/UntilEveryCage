import { readable } from 'svelte/store';

/** One document clock, shared across mounted counters and SPA route changes. */
export const documentElapsedMilliseconds = readable(0, set => {
  if (typeof window === 'undefined') return;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let timer: number | undefined;
  const update = () => set(Math.max(0, performance.now()));
  const stop = () => { if (timer !== undefined) window.clearInterval(timer); timer = undefined; };
  const sync = () => {
    stop();
    if (document.hidden) return;
    update();
    timer = window.setInterval(update, reducedMotion.matches ? 1000 : 1000 / 30);
  };
  document.addEventListener('visibilitychange', sync);
  reducedMotion.addEventListener('change', sync);
  sync();
  return () => {
    stop();
    document.removeEventListener('visibilitychange', sync);
    reducedMotion.removeEventListener('change', sync);
  };
});

export function estimateSinceDocumentOpen(rate: number, elapsedMilliseconds: number) {
  if (!Number.isFinite(rate) || rate <= 0 || !Number.isFinite(elapsedMilliseconds) || elapsedMilliseconds <= 0) return 0;
  return Math.floor(rate * elapsedMilliseconds / 1000);
}
