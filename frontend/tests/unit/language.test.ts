import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

describe('language selection', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.lang = 'en';
    vi.resetModules();
  });

  it('starts in English and falls back to source English for missing translations', async () => {
    const { language, tr } = await import('../../src/app/language');
    expect(get(language)).toBe('en');
    expect(tr('Map', 'en')).toBe('Map');
    expect(tr('A future untranslated label', 'es')).toBe('A future untranslated label');
  });

  it('stores an explicit Spanish choice and updates the document language', async () => {
    const { language, tr } = await import('../../src/app/language');
    language.set('es');
    expect(localStorage.getItem('uec-language')).toBe('es');
    expect(document.documentElement.lang).toBe('es');
    expect(tr('Map', 'es')).toBe('Mapa');
  });

  it('restores a prior explicit Spanish choice', async () => {
    localStorage.setItem('uec-language', 'es');
    const { language } = await import('../../src/app/language');
    expect(get(language)).toBe('es');
  });
});
