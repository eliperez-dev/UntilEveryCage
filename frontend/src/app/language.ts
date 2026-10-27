import { writable } from 'svelte/store';
import { es, type LocaleMessages } from './locales/es';

export const LANGUAGE_OPTIONS = [
  { code: 'en', name: 'English' }, { code: 'es', name: 'Español' },
  { code: 'fr', name: 'Français' }, { code: 'de', name: 'Deutsch' },
  { code: 'nl', name: 'Nederlands' }, { code: 'da', name: 'Dansk' },
] as const;
export type Language = typeof LANGUAGE_OPTIONS[number]['code'];
export const isLanguage = (value: unknown): value is Language => LANGUAGE_OPTIONS.some(option => option.code === value);
const storageKey = 'uec-language';
function storedLanguage(): Language {
  try { const value = typeof localStorage === 'undefined' ? null : localStorage.getItem(storageKey); return isLanguage(value) ? value : 'en'; }
  catch { return 'en'; }
}
const preferred = storedLanguage();
let active: Language = preferred === 'es' ? 'es' : 'en';
const selected = writable<Language>(active);
export const languageLoadState = writable<{ state: 'idle' | 'loading' | 'failed'; requested: Language }>({ state: 'idle', requested: preferred });
const dictionaries: Partial<Record<Language, LocaleMessages>> = { es };
const dictionaryUrls = {
  fr: new URL('./locales/fr.json', import.meta.url).href,
  de: new URL('./locales/de.json', import.meta.url).href,
  nl: new URL('./locales/nl.json', import.meta.url).href,
  da: new URL('./locales/da.json', import.meta.url).href,
};
const failedLoads = new Set<Language>();
async function loadDictionary(value: keyof typeof dictionaryUrls): Promise<LocaleMessages> {
  const response = await fetch(dictionaryUrls[value], { credentials: 'omit', cache: failedLoads.has(value) ? 'reload' : 'force-cache' });
  if (!response.ok) throw new Error('Locale unavailable');
  const messages: unknown = await response.json();
  if (!messages || typeof messages !== 'object' || Array.isArray(messages) || Object.keys(messages).length !== Object.keys(es).length || Object.keys(es).some(key => typeof (messages as Record<string, unknown>)[key] !== 'string' || !(messages as Record<string, string>)[key]?.trim())) throw new Error('Locale invalid');
  return messages as LocaleMessages;
}
let generation = 0;
export async function selectLanguage(value: Language): Promise<boolean> {
  if (!isLanguage(value)) return false;
  const request = ++generation;
  if (value !== 'en' && !dictionaries[value]) {
    languageLoadState.set({ state: 'loading', requested: value });
    try { dictionaries[value] = await loadDictionary(value as keyof typeof dictionaryUrls); failedLoads.delete(value); }
    catch { failedLoads.add(value); if (request === generation) languageLoadState.set({ state: 'failed', requested: value }); return false; }
  }
  if (request !== generation) return false;
  active = value;
  if (typeof document !== 'undefined') document.documentElement.lang = value;
  try { if (typeof localStorage !== 'undefined') localStorage.setItem(storageKey, value); } catch { /* Preferences may be blocked. */ }
  selected.set(value);
  languageLoadState.set({ state: 'idle', requested: value });
  return true;
}
// Keep the existing synchronous store interface for already-loaded English/Spanish.
export const language = { subscribe: selected.subscribe, set: (value: Language) => { void selectLanguage(value); } };
if (typeof document !== 'undefined') document.documentElement.lang = active;
// Do not persist the temporary English fallback over a saved lazy locale.
export const languageReady = preferred !== active ? selectLanguage(preferred) : Promise.resolve(true);
export function tr(source: string, value: Language = active): string {
  return value === 'en' ? source : dictionaries[value]?.[source as keyof LocaleMessages] ?? source;
}
