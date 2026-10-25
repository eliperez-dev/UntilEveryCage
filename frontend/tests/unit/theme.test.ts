import { afterEach, describe, expect, it, vi } from 'vitest';
import { getTheme, setTheme, subscribeTheme } from '../../src/features/theme/theme';

afterEach(() => {
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.style.removeProperty('color-scheme');
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('theme state', () => {
  it('uses dark when no explicit theme exists', () => {
    expect(getTheme()).toBe('dark');
    expect(localStorage.getItem('uec-theme')).toBeNull();
  });

  it('applies and persists a choice, and notifies mounted controls', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeTheme(listener);
    setTheme('light');
    expect(getTheme()).toBe('light');
    expect(document.documentElement.style.colorScheme).toBe('light');
    expect(localStorage.getItem('uec-theme')).toBe('light');
    expect(listener).toHaveBeenCalledWith('light');
    unsubscribe();
    setTheme('dark');
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('keeps the in-page choice active if storage is denied', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Denied', 'SecurityError'); });
    expect(() => setTheme('light')).not.toThrow();
    expect(getTheme()).toBe('light');
    expect(document.documentElement.style.colorScheme).toBe('light');
  });
});
