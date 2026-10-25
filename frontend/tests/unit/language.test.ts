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

  it('translates generated RTE and unspecified activity labels and shared business-name graph labels', async () => {
    const { tr } = await import('../../src/app/language');
    expect(tr('RTE meat processing', 'es')).toBe('Procesamiento de carne lista para consumir (RTE)');
    expect(tr('RTE poultry processing', 'es')).toBe('Procesamiento de aves listas para consumir (RTE)');
    expect(tr('RTE processing', 'es')).toBe('Procesamiento listo para consumir (RTE)');
    expect(tr('RTE unspecified meat processing', 'es')).toBe('Procesamiento de carne no especificada lista para consumir (RTE)');
    expect(tr('RTE unspecified poultry processing', 'es')).toBe('Procesamiento de aves no especificadas listas para consumir (RTE)');
    expect(tr('RTE unspecified processing', 'es')).toBe('Procesamiento no especificado listo para consumir (RTE)');
    expect(tr('Unspecified meat processing', 'es')).toBe('Procesamiento de carne no especificada');
    expect(tr('Unspecified poultry processing', 'es')).toBe('Procesamiento de aves no especificadas');
    expect(tr('Unspecified processing', 'es')).toBe('Procesamiento no especificado');
    expect(tr('Shared business name', 'es')).toBe('Nombre comercial compartido');
    expect(tr('RTE meat processing', 'en')).toBe('RTE meat processing');
    expect(tr('USDA source-native evidence', 'es')).toBe('USDA source-native evidence');
  });

  it('translates the release-help strings shown in Tools', async () => {
    const { tr } = await import('../../src/app/language');
    expect(tr('No verified public release loaded', 'es')).toBe('No se ha cargado una versión pública verificada');
    expect(tr('Release metadata from the active public map.', 'es')).toBe('Metadatos de versión del mapa público activo.');
    expect(tr('Release selection is available from the map.', 'es')).toBe('La selección de versión está disponible desde el mapa.');
  });
});
