import { describe, expect, it, vi } from 'vitest';
import { documentElapsedMilliseconds, estimateSinceDocumentOpen } from '../../src/features/counter/documentElapsed';

describe('since-document-open estimates', () => {
  it('uses full elapsed time and exact rates instead of accumulating rounded ticks', () => {
    expect(estimateSinceDocumentOpen(2779, 0)).toBe(0);
    expect(estimateSinceDocumentOpen(2779, 1000)).toBe(2779);
    expect(estimateSinceDocumentOpen(65671, 1000)).toBe(65671);
    expect(estimateSinceDocumentOpen(140 / 60, 60000)).toBe(140);
    expect(estimateSinceDocumentOpen(2, 300000)).toBe(600);
    expect(estimateSinceDocumentOpen(2779, -1)).toBe(0);
  });

  it('shares one timer, suspends hidden updates and retains document time across remounts', () => {
    vi.useFakeTimers();
    const oldMedia = Object.getOwnPropertyDescriptor(window, 'matchMedia');
    const oldHidden = Object.getOwnPropertyDescriptor(document, 'hidden');
    let now = 0, hidden = false;
    const media = Object.assign(new EventTarget(), { matches: false });
    Object.defineProperty(window, 'matchMedia', { configurable: true, value: () => media });
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    const interval = vi.spyOn(window, 'setInterval');
    const stop: (() => void)[] = [];
    let latest = -1;
    try {
      stop.push(documentElapsedMilliseconds.subscribe(value => latest = value));
      stop.push(documentElapsedMilliseconds.subscribe(() => {}));
      expect(latest).toBe(0);
      expect(vi.getTimerCount()).toBe(1);
      expect(interval.mock.calls[0]?.[1]).toBeCloseTo(1000 / 30);
      now = 1000; vi.advanceTimersByTime(34); expect(latest).toBe(1000);
      hidden = true; document.dispatchEvent(new Event('visibilitychange'));
      expect(vi.getTimerCount()).toBe(0);
      now = 12000; media.matches = true; media.dispatchEvent(new Event('change'));
      expect(latest).toBe(1000);
      hidden = false; document.dispatchEvent(new Event('visibilitychange'));
      expect(latest).toBe(12000);
      expect(interval.mock.calls.at(-1)?.[1]).toBe(1000);
      stop.pop()!(); expect(vi.getTimerCount()).toBe(1);
      stop.pop()!(); expect(vi.getTimerCount()).toBe(0);
      now = 22000; stop.push(documentElapsedMilliseconds.subscribe(value => latest = value));
      expect(latest).toBe(22000);
    } finally {
      stop.forEach(unsubscribe => unsubscribe());
      vi.restoreAllMocks(); vi.useRealTimers();
      if (oldMedia) Object.defineProperty(window, 'matchMedia', oldMedia); else delete (window as any).matchMedia;
      if (oldHidden) Object.defineProperty(document, 'hidden', oldHidden); else delete (document as any).hidden;
    }
  });
});
