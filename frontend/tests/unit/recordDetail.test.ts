import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// The current Vitest config intentionally does not compile Svelte components;
// these checks pin the safety and disclosure contract of this shared surface.
const component = readFileSync(resolve(process.cwd(), 'src/app/RecordDetail.svelte'), 'utf8');

describe('private preview record detail surface', () => {
  it('renders absent identity as unavailable and keeps optional fields conditional', () => {
    expect(component).toContain("?? 'Name unavailable'");
    expect(component).toContain('{#if activity}');
    expect(component).toContain('{#if evidence}');
    expect(component).toContain('{#if retrieved}');
    expect(component).toContain('{#if observed}');
    expect(component).toContain('PRIVATE DEVELOPMENT PREVIEW · NOT PUBLICATION-APPROVED');
  });

  it('labels exact, approximate, and unmapped placement distinctly and includes review context', () => {
    expect(component).toContain('Source coordinate · review status shown below');
    expect(component).toContain('City reference · approximate');
    expect(component).toContain('Coarse city/postal area');
    expect(component).toContain('Approximate source coordinate');
    expect(component).toContain('Unmapped · no map location supplied');
    expect(component).toContain('Coordinate review');
    expect(component).toContain('Factual review');
    expect(component).toContain('Privacy screening');
    expect(component).toContain('Project approval');
    expect(component).toContain("raw.replace(/[_-]+/g, ' ')");
    expect(component).toContain('{humanizeValue(coordinateStatus)}');
    expect(component).toContain('{humanizeValue(record.coordinatePrecision)}');
  });

  it('accepts only HTTPS source links and offers a stable record URL copy action', () => {
    expect(component).toContain("url.protocol === 'https:'");
    expect(component).toContain('rel="noopener noreferrer"');
    expect(component).toContain("${window.location.origin}${window.location.pathname}#/records/${encodeURIComponent(id)}");
    expect(component).toContain('Copy stable record URL');
    expect(component).toContain("'sourceRecordId' in record ? record.sourceRecordId : null");
  });

  it('does not invent a graph or render unavailable API fields as placeholders', () => {
    expect(component).not.toContain('Connections');
    expect(component).not.toContain('Not available in this release');
    expect(component).toContain('Source origin does not establish accuracy');
  });
});
