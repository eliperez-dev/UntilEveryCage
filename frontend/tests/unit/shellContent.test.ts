import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { tr } from '../../src/app/language';

const masthead = readFileSync(resolve(process.cwd(), 'src/app/PreviewMasthead.svelte'), 'utf8');
const contributions = readFileSync(resolve(process.cwd(), 'src/app/CommunityContributions.svelte'), 'utf8');
const intake = readFileSync(resolve(process.cwd(), 'src/app/contributions/ContributionForm.svelte'), 'utf8');
const contribute = readFileSync(resolve(process.cwd(), 'src/app/ContributePage.svelte'), 'utf8');
const api = readFileSync(resolve(process.cwd(), 'src/app/ApiPage.svelte'), 'utf8');
const picker = readFileSync(resolve(process.cwd(), 'src/app/ContributionPinPicker.svelte'), 'utf8');
const mapSurface = readFileSync(resolve(process.cwd(), 'src/design-lab/components/MapSurface.svelte'), 'utf8');
const aphisReports = readFileSync(resolve(process.cwd(), 'src/app/AphisReports.svelte'), 'utf8');
const publicRecord = readFileSync(resolve(process.cwd(), 'src/app/PublicRecord.svelte'), 'utf8');
const language = readFileSync(resolve(process.cwd(), 'src/app/locales/es.ts'), 'utf8');

describe('normal shell content', () => {
  it('uses canonical primary taxonomy values for the facility activity selector', () => {
    expect(intake).toContain('name="claimed_activity"');
    expect(intake).toContain('TAXONOMY_PRIMARY_KEYS as category');
    expect(intake).toContain('CATEGORY_PRESENTATIONS[category].label');
    expect(intake).not.toContain('name="claimed_activity" maxlength');
    expect(intake).toContain("'Other / Unknown (unclassified)'");
    expect(language).toContain("'Other / Unknown (unclassified)': 'Otro / Desconocido (sin clasificar)'");
  });

  it('keeps map tools on the map and uses the regular V1 contribution pin in production', () => {
    expect(masthead).toContain("{#if current === 'map'}");
    expect(mapSurface).toContain('mode !== "synthetic" && debugEnabled');
    expect(mapSurface).not.toContain('import.meta.env.DEV && mode !== "synthetic" && debugEnabled');
    expect(picker).toContain('v1-pins/marker-icon-2x-red.png');
    expect(picker).not.toContain('rotate(-45deg)');
  });

  it('keeps public community browsing tied to a published release, separately from intake', () => {
    expect(contribute).toContain("current('community')");
    expect(contribute).toContain('{#if communityReleasePublished}<a href={utilityHref(\'community\')}>');
    expect(api).toContain("current('community')");
    expect(api).toContain('{#if communityReleaseAvailable}<option value="community">{tr(\'Community submissions\', $language)}</option>{/if}');
    expect(api).toContain('selectedReleaseId: selectedFromRoute');
    expect(api).toContain('repository.current(profile, controller.signal, chosenId)');
    expect(api).toContain("{tr('API release ID:', $language)} <code>{releaseId}</code>");
    expect(tr('API release ID:', 'en')).toBe('API release ID:');
    expect(api).not.toContain("limit: '1'");
  });

  it('keeps the map-selected historic release in API and download links', () => {
    const app = readFileSync(resolve(process.cwd(), 'src/app/App.svelte'), 'utf8');
    expect(app).toContain('selectedReleaseId={new URLSearchParams(route.returnMapHref?.split(\'?\')[1] ?? \'\').get(\'release_id\')}');
    expect(api).toContain("...(releaseId ? { release_id: releaseId } : {})");
    expect(api).toContain("aria-label={tr('Public release', $language)}");
    expect(language).toContain("'Public release': 'Versión pública'");
  });

  it('translates APHIS and record-detail chrome without translating source dates or identifiers', () => {
    expect(aphisReports).toContain("tr('Annual report', $language)");
    expect(aphisReports).toContain("tr('Inspection', $language)");
    expect(aphisReports).toContain('FY${reference.event_period}');
    expect(aphisReports).toContain('${reference.event_date}');
    expect(publicRecord).toContain("tr('Loading record…', $language)");
    expect(publicRecord).toContain("<summary>{tr('Source and review', $language)}</summary>");
    expect(language).toContain("'Annual report': 'Informe anual'");
    expect(language).toContain("'Inspection': 'Inspección'");
    expect(tr('Annual report', 'en')).toBe('Annual report');
    expect(tr('Missing Spanish entry', 'es')).toBe('Missing Spanish entry');
  });

  it('loads published community browsing independently of intake and stops retrying after one failed lookup', () => {
    expect(contributions).toContain("page !== 'claims' && page !== 'claim-detail'");
    expect(contributions).toContain("page === 'claims' && !claimsAttempted && !claims && !busy");
    expect(contributions).toContain('claimsAttempted = true');
    expect(contributions).toContain("communityRelease.trim() || releaseId.trim() || await repository.currentCommunityReleaseId()");
    expect(contributions).toContain('Published community submissions could not be loaded. There may be no active community release.');
    expect(contributions).toContain('No privacy-screened submissions are published in the current community release.');
    expect(contributions).not.toContain('Open community profile');
  });

});
