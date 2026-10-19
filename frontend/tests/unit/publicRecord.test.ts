import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const component = readFileSync(resolve(process.cwd(), 'src/app/PublicRecord.svelte'), 'utf8');

describe('public record detail facts', () => {
  it('renders only available allowlisted source facts and preserves source flags', () => {
    expect(component).toContain('Source facts');
    expect(component).toContain('Also known as');
    expect(component).toContain('Establishment ID');
    expect(component).not.toContain('Source volume categories');
    expect(component).toContain(".join(', ')");
    expect(component).toContain('record.sourceFacts.speciesSlaughtered');
    expect(component).toContain('record.sourceFacts.processingActivities');
  });

  it('uses a concise precision and method row instead of a repeated limitation wall', () => {
    expect(component).toContain("record.evidence?.geometryProvenance?.method");
    expect(component).not.toContain('A source record does not establish current operation');
    expect(component).not.toContain('Facility candidate');
    expect(component).not.toContain('Unclassified');
  });

  it('keeps source, date, precision, and lifecycle metadata while omitting internal governance fields', () => {
    expect(component).toContain('Source origin');
    expect(component).toContain('Observed');
    expect(component).toContain('Retrieved');
    expect(component).toContain('Lifecycle');
    expect(component).not.toContain('<dt>Factual review</dt>');
    expect(component).not.toContain('<dt>Privacy screening</dt>');
    expect(component).not.toContain('<dt>Project approval</dt>');
  });
});
