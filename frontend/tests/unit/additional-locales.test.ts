import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { es } from '../../src/app/locales/es';
import fr from '../../src/app/locales/fr';
import de from '../../src/app/locales/de';
import nl from '../../src/app/locales/nl';
import da from '../../src/app/locales/da';
const dictionaries = { fr, de, nl, da };
const response = (dictionary: unknown) => ({ ok: true, json: async () => dictionary });
let fetcher: ReturnType<typeof vi.fn>;

describe('additional interface locales', () => {
  beforeEach(() => {
    vi.resetModules(); vi.restoreAllMocks(); localStorage.clear();
    fetcher = vi.fn(async (input: string) => response(dictionaries[/\/(fr|de|nl|da)\.json$/.exec(input)![1] as keyof typeof dictionaries]));
    vi.stubGlobal('fetch', fetcher);
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it('gives every additional locale the complete source catalog and real public translations', () => {
    const keys = Object.keys(es).sort();
    for (const dictionary of Object.values(dictionaries)) {
      expect(Object.keys(dictionary).sort()).toEqual(keys);
      for (const value of Object.values(dictionary)) expect(value.trim().length).toBeGreaterThan(0);
      for (const source of ['Map', 'Search map', 'Add a facility', 'Clear area search', 'Save this link. You cannot access your submission again without it.'] as const) expect(dictionary[source]).not.toBe(source);
    }
  });
  it('loads every new locale and keeps unknown source identifiers unchanged', async () => {
    const { selectLanguage, language, tr } = await import('../../src/app/language');
    for (const locale of ['fr', 'de', 'nl', 'da'] as const) {
      expect(await selectLanguage(locale)).toBe(true);
      expect(get(language)).toBe(locale); expect(document.documentElement.lang).toBe(locale);
      expect(localStorage.getItem('uec-language')).toBe(locale); expect(tr('us.fsis', locale)).toBe('us.fsis');
    }
    const calls = fetcher.mock.calls.length; await selectLanguage('fr'); expect(fetcher.mock.calls).toHaveLength(calls);
  });
  it('restores a saved lazy locale without overwriting it with temporary English', async () => {
    localStorage.setItem('uec-language', 'fr');
    const { language, languageReady, tr } = await import('../../src/app/language');
    expect(localStorage.getItem('uec-language')).toBe('fr');
    await languageReady; expect(get(language)).toBe('fr'); expect(tr('Map', 'fr')).toBe('Carte');
  });
  it('keeps the active locale on failure and Retry refetches and recovers', async () => {
    fetcher.mockRejectedValueOnce(new Error('Synthetic unavailable asset'));
    const { selectLanguage, language, languageLoadState } = await import('../../src/app/language');
    await selectLanguage('es'); expect(await selectLanguage('fr')).toBe(false);
    expect(get(language)).toBe('es'); expect(document.documentElement.lang).toBe('es');
    expect(localStorage.getItem('uec-language')).toBe('es'); expect(get(languageLoadState).state).toBe('failed');
    expect(await selectLanguage('fr')).toBe(true); expect(get(language)).toBe('fr');
    expect(fetcher.mock.calls[1]?.[1]).toMatchObject({ cache: 'reload', credentials: 'omit' });
  });
  it('rejects an incomplete catalog without changing language', async () => {
    fetcher.mockResolvedValueOnce(response({ Map: 'Invalid partial catalog' }));
    const { selectLanguage, language } = await import('../../src/app/language');
    expect(await selectLanguage('fr')).toBe(false); expect(get(language)).toBe('en');
  });
  it('does not apply a stale locale after a newer choice', async () => {
    let finish: ((value: ReturnType<typeof response>) => void) | undefined;
    fetcher.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const { selectLanguage, language } = await import('../../src/app/language');
    const pending = selectLanguage('fr'); await vi.waitFor(() => expect(finish).not.toBeUndefined());
    await selectLanguage('es'); finish!(response(fr)); await pending;
    expect(get(language)).toBe('es'); expect(localStorage.getItem('uec-language')).toBe('es');
  });
  it('handles unsupported preferences and unavailable storage', async () => {
    localStorage.setItem('uec-language', 'unsupported');
    const { language, selectLanguage } = await import('../../src/app/language');
    expect(get(language)).toBe('en');
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Synthetic blocked storage'); });
    expect(await selectLanguage('nl')).toBe(true); expect(document.documentElement.lang).toBe('nl');
  });
});
