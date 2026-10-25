import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const field = readFileSync(resolve(process.cwd(), 'src/design-lab/variants/field/Field.svelte'), 'utf8');
const designLab = readFileSync(resolve(process.cwd(), 'src/design-lab/DesignLab.svelte'), 'utf8');

describe('search UI repair contract', () => {
  it('communicates the complete candidate match count separately from the loaded page', () => {
    expect(field).toContain('candidateTotalCount?: number | null');
    expect(field).toContain('`${candidateTotalCount} matching · ${resultCount} shown`');
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
    expect(field).toContain('<details class="filters">');
    expect(field).toMatch(/<summary>\{tr\('Filters', \$language\)\}/);
    expect(field).toMatch(/<fieldset><legend>Country<\/legend>/);
    expect(field).toMatch(/<fieldset><legend>Source<\/legend>/);
    expect(field).toMatch(/<fieldset><legend>Activity category<\/legend>/);
    expect(field).toMatch(/<label><input type="checkbox"/);
    expect(field).toContain('min-height: 2rem');
  });

  it('offers the single clear action whenever a query, source, or filter is active', () => {
    expect(field).toContain('(state.query.trim() ? 1 : 0)');
    expect(field).toContain('(state.sourceId ? 1 : 0)');
    expect(field).toContain('dispatch({ type: "reset-filters" })');
  });
});
