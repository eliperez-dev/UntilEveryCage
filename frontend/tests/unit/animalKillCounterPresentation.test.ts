import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const counter = readFileSync(resolve(process.cwd(), 'src/app/AnimalKillCounter.svelte'), 'utf8');

describe('legacy counter presentation', () => {
  it('labels the model and keeps source and method expandable', () => {
    expect(counter).toContain('<h2 id="estimate-title">Estimated animals killed</h2>');
    expect(counter).toContain('Since this page opened · inherited V1 annual estimates');
    expect(counter).toContain('<summary>Source and method</summary>');
    expect(counter).toContain('edition or year is not retained for some rates');
    expect(counter).not.toContain('2024 global estimates');
  });
});
