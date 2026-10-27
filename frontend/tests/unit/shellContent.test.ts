import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { tr } from '../../src/app/language';

const masthead = readFileSync(resolve(process.cwd(), 'src/app/PreviewMasthead.svelte'), 'utf8');
const about = readFileSync(resolve(process.cwd(), 'src/app/AboutPage.svelte'), 'utf8');
const faq = readFileSync(resolve(process.cwd(), 'src/app/FaqPage.svelte'), 'utf8');
const footer = readFileSync(resolve(process.cwd(), 'src/app/ProjectFooter.svelte'), 'utf8');
const contributions = readFileSync(resolve(process.cwd(), 'src/app/CommunityContributions.svelte'), 'utf8');
const intake = readFileSync(resolve(process.cwd(), 'src/app/contributions/ContributionForm.svelte'), 'utf8');
const contribute = readFileSync(resolve(process.cwd(), 'src/app/ContributePage.svelte'), 'utf8');
const api = readFileSync(resolve(process.cwd(), 'src/app/ApiPage.svelte'), 'utf8');
const field = readFileSync(resolve(process.cwd(), 'src/design-lab/variants/field/Field.svelte'), 'utf8');
const atlas = readFileSync(resolve(process.cwd(), 'src/design-lab/variants/atlas/Atlas.svelte'), 'utf8');
const picker = readFileSync(resolve(process.cwd(), 'src/app/ContributionPinPicker.svelte'), 'utf8');
const mapSurface = readFileSync(resolve(process.cwd(), 'src/design-lab/components/MapSurface.svelte'), 'utf8');
const aphisReports = readFileSync(resolve(process.cwd(), 'src/app/AphisReports.svelte'), 'utf8');
const publicRecord = readFileSync(resolve(process.cwd(), 'src/app/PublicRecord.svelte'), 'utf8');
const language = readFileSync(resolve(process.cwd(), 'src/app/locales/es.ts'), 'utf8');

describe('normal shell content', () => {
  it('keeps release context compact and removes unavailable account controls', () => {
    expect(masthead).toContain('Current release');
    expect(masthead).toContain('shared-tools-menu');
    expect(masthead).toContain('grid-template-columns: minmax(0, 1fr) max-content minmax(0, 1fr);');
    expect(masthead).toContain('justify-content:center; justify-self:center;');
    expect(masthead).toContain('onreleasechange?.(event.currentTarget.value)');
    expect(masthead).not.toContain('Open a record to view its available release history.');
    expect(masthead).not.toContain('Historical views follow current privacy restrictions.');
    expect(masthead).not.toContain('Release</button>');
    expect(masthead).toContain('text-overflow:ellipsis');
    expect(masthead).not.toContain('Account unavailable');
    expect(masthead).not.toContain('Preview release');
  });

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

  it('keeps the supplied manifesto and counter while embedding the concise FAQ in About', () => {
    expect(about).toContain('About Until Every Cage is Empty');
    expect(about).toContain('The Architecture of Silence');
    expect(about).toContain("{tr('Until Every Cage is Empty', $language)}</h2>");
    expect(language).toContain("'Until Every Cage is Empty': 'Hasta que todas las jaulas estén vacías'");
    expect(about).toContain('<aside class="about-counter-slot" aria-label="Animal counter"><AnimalKillCounter /></aside>');
    expect(about).toContain('assets/icon.png');
    expect(about).toContain('about-logo');
    expect(about).not.toContain('Explore and contribute');
    expect(about).not.toContain('Common questions');
    expect(about).not.toContain('estimate-number');
    expect(about).not.toContain('Sources and methods');
    expect(faq).toContain('How the data reaches the map');
    expect(faq).toContain('Government datasets are collected, cleaned and standardized, with links back to their sources. Address lookups add coordinates, and matching connects related records. Dated releases supply the map, search and downloads through a Rust API.');
    expect(faq).not.toContain('Sources and methods');
    expect(faq).not.toContain('Its sources and method are shown with the counter');
    expect(faq).not.toContain('PostgreSQL with PostGIS');
    for (const topic of ['suggest a facility', 'add evidence', 'suggest a correction', 'possible duplicate', 'privacy review', 'private tracking link', 'report a bug']) expect(faq).toContain(topic);
    expect(faq).not.toContain('email-notification');
    expect(about).not.toContain('<video');
  });

  it('localizes FAQ connectors and uses theme-aware accessible colors', () => {
    expect(faq).toContain("{tr('or', $language)}");
    expect(faq).toContain("{tr('You can also join', $language)}");
    expect(faq).not.toContain('También puedes unirte a');
    expect(faq).not.toContain('> o <');
    expect(faq).toContain('color:var(--ink)');
    expect(faq).toContain('color:var(--ink-muted)');
    expect(faq).toContain('color:var(--link)');
    expect(faq).not.toContain('#dce8d9');
    expect(faq).not.toContain('#c6d0c5');
  });

  it('restores the living-project footer with a backend version component', () => {
    expect(footer).toContain("{tr('An independent, open-source, ad-free project.', $language)}</p>");
    expect(language).toContain("'An independent, open-source, ad-free project.': 'Un proyecto independiente, de código abierto y sin anuncios.'");
    expect(footer).not.toContain('Feedback and questions are welcome.');
    for (const url of ['mailto:untileverycageproject@protonmail.com', 'https://discord.gg/wbdTHzAZ4b', 'https://ko-fi.com/untileverycageisempty', 'https://linktr.ee/veganresource', 'https://github.com/eliperez-dev/UntilEveryCage']) expect(footer).toContain(url);
    expect(footer).toContain("{tr('Code is available under', $language)} <a href=\"https://www.gnu.org/licenses/agpl-3.0.html\" target=\"_blank\" rel=\"noreferrer\">AGPLv3 {tr('or later', $language)}</a>");
    expect(tr('or later', 'en')).toBe('or later');
    expect(footer).toContain('CC BY-NC-SA where applicable');
    expect(footer).toContain("{tr('Counter Adapted from', $language)} <a href=\"https://www.adaptt.org/\" target=\"_blank\" rel=\"noreferrer\">ADAPTT</a>.");
    expect(footer).not.toContain('Counter approach adapted');
    expect(picker).toContain('new maplibregl.NavigationControl');
    expect(mapSurface).not.toContain('new maplibregl.NavigationControl');
    expect(masthead).toContain('map-view-tools');
    expect(masthead).toContain('Right-mouse to rotate / Left-mouse to pan');
    expect(masthead).toContain('.map-view-controls');
    expect(mapSurface).not.toContain('class="map-controls-wrap"');
    expect(footer).toContain('Final Nail');
    expect(footer).toContain('<div class="application-version-slot"><ApplicationVersion /></div>');
    expect(footer).not.toContain('v1.5.1');
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
    expect(publicRecord).toContain("<h2 id=\"source-heading\">{tr('Source and review', $language)}</h2>");
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

  it('does not render an empty speculative connections block', () => {
    expect(field).not.toContain('private-preview relationship projection');
    expect(field).not.toContain('EVIDENCE CONNECTIONS');
    expect(field).not.toContain('connections-evidence');
  });

  it('keeps authored atlas labels free of em dashes', () => {
    expect(atlas).toContain('01: RESULTS');
    expect(atlas).not.toContain('01 — RESULTS');
  });
});
