import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// The current Vitest config intentionally does not compile Svelte components;
// these checks pin the safety and disclosure contract of this shared surface.
const component = readFileSync(resolve(process.cwd(), 'src/app/RecordDetail.svelte'), 'utf8');
const designLab = readFileSync(resolve(process.cwd(), 'src/design-lab/DesignLab.svelte'), 'utf8');

describe('private preview record detail surface', () => {
  it('renders a gated identity as not shown and keeps optional fields conditional', () => {
    expect(component).toContain('Name not shown, privacy review pending');
    expect(component).toContain("? 'Name not shown'");
    expect(component).toContain('{#if evidence}');
    expect(component).toContain('{#if retrieved}');
    expect(component).toContain('{#if observed}');
    expect(component).not.toContain('PRIVATE DEVELOPMENT PREVIEW');
    expect(component).not.toContain('Facility candidate');
    expect(component).toContain('Activities and classification');
    expect(component).not.toContain('assignment.taxonomyVersion');
    expect(component).not.toContain('taxonomy.taxonomyVersion');
    expect(component).not.toContain('Primary categories');
  });

  it('labels exact, approximate, and unmapped placement distinctly without exposing internal review fields', () => {
    expect(component).toContain('Source coordinate · review status shown below');
    expect(component).toContain("return 'Approximate location'");
    expect(component).toContain('Source-provided coordinates');
    expect(component).toContain('Unmapped · no map location supplied');
    expect(component).toContain('Coordinate review');
    expect(component).not.toContain('Factual review');
    expect(component).not.toContain('Privacy screening');
    expect(component).not.toContain('Project approval');
    expect(component).toContain("raw.replace(/[_-]+/g, ' ')");
    expect(component).toContain('{displayGeneratedValue(coordinateStatus)}');
    expect(component).toContain('{displayGeneratedValue(record.coordinatePrecision)}');
  });

  it('accepts only HTTPS source links and offers a stable record URL copy action', () => {
    expect(component).toContain("url.protocol === 'https:'");
    expect(component).toContain('rel="noopener noreferrer"');
    expect(component).toContain("serializeRoute({ kind: 'record', facilityId: id");
    expect(component).toContain('Copy facility link');
    expect(component).not.toContain('Copy record ID');
    expect(component).toContain("'sourceRecordId' in record ? record.sourceRecordId : null");
  });

  it('shows a compact copy action in public map previews and keeps the selected release in its URL', () => {
    expect(component).toContain("presentation === 'page' || (presentation === 'rail' && publicRelease)");
    expect(component).toContain("profile: 'official', ...(publicReleaseId ? { releaseId: publicReleaseId } : {})");
    expect(component).toContain('class="share"');
    expect(component).toContain('Copy facility link');
    expect(component).toContain('min-height: 1.75rem');
  });

  it('keeps connections scoped to an active public release', () => {
    expect(component).toContain('publicRelease && publicReleaseId && id');
    expect(component).not.toContain('Not available in this release');
    expect(component).not.toContain('Record source and date are shown below.');
  });

  it('renders compact, allowlisted source facts ahead of the source dates and omits raw volume categories', () => {
    expect(component).toContain('id="source-facts-heading"');
    expect(component).toContain('sourceFacts.alternateNames?.length');
    expect(component).toContain('compactSourceFacts');
    expect(component).not.toContain('Source volume categories');
    expect(component).toContain('Estimated animals slaughtered (last 360 days)');
    expect(component).toContain('Estimated product volume (pounds/month)');
    expect(component).toContain('derivedSourceVolumeRanges');
    expect(component).toContain("{tr('FY ', $language)}{report.fiscalYear} {tr('reported animals', $language)}");
    expect(component.indexOf('id="source-facts-heading"')).toBeLessThan(component.indexOf('id="evidence-heading"'));
  });

  it('keeps public selected-map source facts for the shared detail surface', () => {
    expect(designLab).toContain("...(location.sourceFacts ? { sourceFacts: location.sourceFacts } : {}),");
  });

  it('keeps the mobile copy controls after the complete evidence flow instead of pinning them over it', () => {
    expect(component).not.toContain('.page footer {\n      position: sticky;');
  });
});
