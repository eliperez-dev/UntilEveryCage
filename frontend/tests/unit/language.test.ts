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

  it('falls back to English when storage reads are unavailable', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('storage denied'); });
    const { language } = await import('../../src/app/language');
    expect(get(language)).toBe('en');
  });

  it('translates APHIS report controls and the masthead theme toggle name', async () => {
    const { tr } = await import('../../src/app/language');
    expect(tr('Annual reports', 'es')).toBe('Informes anuales');
    expect(tr('Fetch inspection reports', 'es')).toBe('Cargar informes de inspección');
    expect(tr('No inspection reports found.', 'es')).toBe('No se encontraron informes de inspección.');
    expect(tr('Light theme', 'es')).toBe('Tema claro');
    expect(tr('Dark theme', 'es')).toBe('Tema oscuro');
  });

  it('translates project-generated record metadata without changing source identifiers', async () => {
    const { tr } = await import('../../src/app/language');
    expect(tr('Establishment ID', 'es')).toBe('ID del establecimiento');
    expect(tr('Source origin', 'es')).toBe('Origen de la fuente');
    expect(tr('Source-provided coordinates', 'es')).toBe('Coordenadas proporcionadas por la fuente');
    expect(tr('Processing and preparation', 'es')).toBe('Procesamiento y preparación');
    expect(tr('Add evidence', 'es')).toBe('Añadir evidencia');
    expect(tr('us.fsis', 'es')).toBe('us.fsis');
  });

  it('translates generated NRTE activity labels while preserving the acronym', async () => {
    const { tr } = await import('../../src/app/language');
    expect(tr('Chicken processing', 'es')).toBe('Procesamiento de pollo');
    expect(tr('NRTE chicken processing', 'es')).toBe('Procesamiento de pollo (NRTE)');
    expect(tr('NRTE poultry processing', 'es')).toBe('Procesamiento de aves (NRTE)');
    expect(tr('NRTE processing', 'es')).toBe('Procesamiento (NRTE)');
  });
});
