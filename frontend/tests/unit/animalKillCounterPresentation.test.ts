import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const counter = readFileSync(resolve(process.cwd(), 'src/app/AnimalKillCounter.svelte'), 'utf8');

describe('legacy counter presentation', () => {
  it('shows the counter values without an on-screen source and method disclosure', () => {
    expect(counter).toContain('<h2 id="estimate-title">Estimated animals killed</h2>');
    expect(counter).toContain('Estimated since you opened this page.');
    expect(counter).not.toContain('Source and method');
    expect(counter).not.toContain('edition or year is not retained');
    expect(counter).not.toContain('2024 global estimates');
  });
});
