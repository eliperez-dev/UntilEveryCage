import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// The current Vitest config intentionally does not compile Svelte components;
// these checks pin the safety and disclosure contract of this shared surface.
const component = readFileSync(resolve(process.cwd(), 'src/app/RecordDetail.svelte'), 'utf8');

describe('private preview record detail surface', () => {
  it('renders a gated identity as not shown and keeps optional fields conditional', () => {
    expect(component).toContain('Name not shown, privacy review pending');
    expect(component).toContain("? 'Name not shown'");
    expect(component).toContain('{#if activity}');
    expect(component).toContain('{#if evidence}');
    expect(component).toContain('{#if retrieved}');
    expect(component).toContain('{#if observed}');
    expect(component).not.toContain('PRIVATE DEVELOPMENT PREVIEW');
    expect(component).not.toContain('Facility candidate');
    expect(component).toContain('Activities and classification');
    expect(component).toContain('Classification provenance');
    expect(component).toContain('assignment.taxonomyVersion');
  });

  it('labels exact, approximate, and unmapped placement distinctly and includes review context', () => {
    expect(component).toContain('Source coordinate · review status shown below');
    expect(component).toContain('City reference · approximate');
    expect(component).toContain('Coarse city/postal area');
    expect(component).toContain('Approximate source coordinate');
    expect(component).toContain('Source-provided coordinate, precision unverified');
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
    expect(component).toContain('Copy record link');
    expect(component).toContain('Copy record ID');
    expect(component).toContain("'sourceRecordId' in record ? record.sourceRecordId : null");
  });

  it('does not invent a graph or render unavailable API fields as placeholders', () => {
    expect(component).not.toContain('Connections');
    expect(component).not.toContain('Not available in this release');
    expect(component).not.toContain('Record source and date are shown below.');
  });

  it('renders compact, allowlisted source facts ahead of the source dates and omits raw volume categories', () => {
    expect(component).toContain('id="source-facts-heading"');
    expect(component).toContain('sourceFacts.alternateNames?.length');
    expect(component).toContain('compactSourceFacts');
    expect(component).toContain('nativeActivity');
    expect(component).not.toContain('Source volume categories');
    expect(component).toContain('Estimated animals slaughtered (last 360 days)');
    expect(component).toContain('Estimated product volume (pounds/month)');
    expect(component).toContain('derivedSourceVolumeRanges');
    expect(component).toContain('FY{report.fiscalYear} reported animals');
    expect(component.indexOf('id="source-facts-heading"')).toBeLessThan(component.indexOf('id="evidence-heading"'));
  });

  it('keeps the mobile copy controls after the complete evidence flow instead of pinning them over it', () => {
    expect(component).not.toContain('.page footer {\n      position: sticky;');
  });
});
