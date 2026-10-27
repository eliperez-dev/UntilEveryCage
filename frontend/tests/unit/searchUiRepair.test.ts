import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const field = readFileSync(resolve(process.cwd(), 'src/design-lab/variants/field/Field.svelte'), 'utf8');
const designLab = readFileSync(resolve(process.cwd(), 'src/design-lab/DesignLab.svelte'), 'utf8');

describe('search UI repair contract', () => {
  it('communicates the complete candidate match count separately from the loaded page', () => {
    expect(field).toContain('candidateTotalCount?: number | null');
    expect(field).toContain("tr('{count} matching · {shown} shown', $language)");
    expect(field).toContain("replace('{count}', new Intl.NumberFormat($language).format(candidateTotalCount))");
    expect(field).toContain("replace('{shown}', new Intl.NumberFormat($language).format(resultCount))");
    expect(field).toContain('`Load more (${resultCount} of ${candidateTotalCount})`');
  });

  it('keeps a candidate search query and its filtered total through pagination', () => {
    const candidateLoad = designLab.match(/if \(mode === 'candidate-preview'\) \{([\s\S]*?)\n      \}/)?.[1];

    expect(candidateLoad).toContain('q: query');
    expect(candidateLoad).toContain('cursor: reset ? null : nextCursor');
    expect(candidateLoad).toContain('candidateTotalCount = page.totalCount');
    expect(candidateLoad).toContain('reset ? mapped :');
  });

  it('keeps filters keyboard-operable and gives each control an accessible reading target', () => {
    expect(field).toContain('<details class="filters" bind:this={$filterDisclosure}');
    expect(field).toMatch(/<summary><svg[\s\S]*?<\/svg>\{tr\('Filters', \$language\)\}/);
    expect(field).toContain(`<fieldset aria-label="{tr('Country', $language)}">`);
    expect(field).toContain(`<fieldset aria-label="{tr('Source', $language)}">`);
    expect(field).toContain(`<summary><span>{tr('Country', $language)}</span>`);
    expect(field).toContain(`<summary><span>{tr('Source', $language)}</span>`);
    expect(field).toContain("state.filters.countries.map(countryName).join(', ')");
    expect(field).toContain("state.filters.sources.map(sourceName).join(', ')");
    expect(field).toMatch(/<fieldset><legend>\{tr\('Activity category', \$language\)\}<\/legend>/);
    expect(field).toMatch(/<label><input type="checkbox"/);
    expect(field).toContain('min-height: 2.75rem');
  });

  it('offers the single clear action whenever a query, source, or filter is active', () => {
    expect(field).toContain('(state.query.trim() ? 1 : 0)');
    expect(field).toContain('(state.sourceId ? 1 : 0)');
    expect(field).toContain('onclick={clearSearch}');
    expect(field).toContain("dispatch({ type: 'reset-filters' });");
  });
});
