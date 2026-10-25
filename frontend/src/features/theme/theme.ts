export type Theme = 'dark' | 'light';

const STORAGE_KEY = 'uec-theme';
const listeners = new Set<(theme: Theme) => void>();

export function getTheme(): Theme {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Theme remains active for this page even when storage is unavailable.
  }
  for (const listener of listeners) listener(theme);
}

export function subscribeTheme(listener: (theme: Theme) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
