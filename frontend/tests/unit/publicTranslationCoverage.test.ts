import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { es } from '../../src/app/locales/es';
import fr from '../../src/app/locales/fr';
import de from '../../src/app/locales/de';
import nl from '../../src/app/locales/nl';
import da from '../../src/app/locales/da';

describe('public translation completeness', () => {
  it('keeps every interface catalog aligned, including count placeholders', () => {
    for (const messages of [fr, de, nl, da]) {
      expect(Object.keys(messages).sort()).toEqual(Object.keys(es).sort());
      for (const [key, value] of Object.entries(messages)) {
        expect(value.trim()).not.toBe('');
        expect((value.match(/\{[a-zA-Z]+\}/g) ?? []).sort()).toEqual((key.match(/\{[a-zA-Z]+\}/g) ?? []).sort());
      }
    }
  });
  it('routes the complete About manifesto through the language catalog', () => {
    const about = readFileSync(resolve(process.cwd(), 'src/app/AboutPage.svelte'), 'utf8');
    expect(about).not.toContain("$language === 'es'");
    for (const key of ['Piglets are castrated and tails are docked without anesthesia. Cows are dehorned with burning irons. Chickens are debeaked with hot blades.', 'The industry knows the public would never accept this reality if they saw it. Therefore, the system is engineered to ensure you never do.', 'Ensure that no facility can hide its operations in the dark.']) {
      expect(about).toContain(`tr(${JSON.stringify(key)}, $language)`);
      for (const messages of [es, fr, de, nl, da]) expect(messages[key]).not.toBe(key);
    }
    expect(about).toContain('<strong>Until Every Cage is Empty</strong>');
  });
});
