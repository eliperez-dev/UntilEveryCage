import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const masthead = readFileSync(resolve(process.cwd(), 'src/app/PreviewMasthead.svelte'), 'utf8');
const about = readFileSync(resolve(process.cwd(), 'src/app/AboutPage.svelte'), 'utf8');
const faq = readFileSync(resolve(process.cwd(), 'src/app/FaqPage.svelte'), 'utf8');
const footer = readFileSync(resolve(process.cwd(), 'src/app/ProjectFooter.svelte'), 'utf8');
const contributions = readFileSync(resolve(process.cwd(), 'src/app/CommunityContributions.svelte'), 'utf8');
const contribute = readFileSync(resolve(process.cwd(), 'src/app/ContributePage.svelte'), 'utf8');
const api = readFileSync(resolve(process.cwd(), 'src/app/ApiPage.svelte'), 'utf8');
const field = readFileSync(resolve(process.cwd(), 'src/design-lab/variants/field/Field.svelte'), 'utf8');
const atlas = readFileSync(resolve(process.cwd(), 'src/design-lab/variants/atlas/Atlas.svelte'), 'utf8');
const picker = readFileSync(resolve(process.cwd(), 'src/app/ContributionPinPicker.svelte'), 'utf8');
const mapSurface = readFileSync(resolve(process.cwd(), 'src/design-lab/components/MapSurface.svelte'), 'utf8');

describe('normal shell content', () => {
  it('keeps release context compact and removes unavailable account controls', () => {
    expect(masthead).toContain('Current release');
    expect(masthead).toContain('shared-tools-menu');
    expect(masthead).toContain('onreleasechange?.(event.currentTarget.value)');
    expect(masthead).toContain('Historical views follow current privacy restrictions.');
    expect(masthead).not.toContain('Release</button>');
    expect(masthead).toContain('text-overflow:ellipsis');
    expect(masthead).not.toContain('Account unavailable');
    expect(masthead).not.toContain('Preview release');
  });

  it('uses canonical primary taxonomy values for the facility activity selector', () => {
    expect(contributions).toContain('name="claimed_activity"');
    expect(contributions).toContain('TAXONOMY_PRIMARY_KEYS as category');
    expect(contributions).toContain('CATEGORY_PRESENTATIONS[category].label');
    expect(contributions).not.toContain('name="claimed_activity" maxlength');
    expect(contributions).toContain('Other / Unknown (unclassified)');
  });

  it('keeps map tools on the map and uses the regular V1 contribution pin in production', () => {
    expect(masthead).toContain("{#if current === 'map'}");
    expect(mapSurface).toContain('mode !== "synthetic" && debugEnabled');
    expect(mapSurface).not.toContain('import.meta.env.DEV && mode !== "synthetic" && debugEnabled');
    expect(picker).toContain('v1-pins/marker-icon-2x-red.png');
    expect(picker).not.toContain('rotate(-45deg)');
  });

  it('keeps the supplied manifesto, counter component, and concise FAQ separate', () => {
    expect(about).toContain('About Until Every Cage is Empty');
    expect(about).toContain('The Architecture of Silence');
    expect(about).toContain('Until Every Cage is Empty</h2>');
    expect(about).toContain('<aside class="about-counter-slot" aria-label="Animal counter"><AnimalKillCounter /></aside>');
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

  it('restores the living-project footer with a backend version component', () => {
    expect(footer).toContain('<p>An independent, open-source, ad-free project.</p>');
    expect(footer).not.toContain('Feedback and questions are welcome.');
    for (const url of ['mailto:untileverycageproject@protonmail.com', 'https://discord.gg/wbdTHzAZ4b', 'https://ko-fi.com/untileverycageisempty', 'https://linktr.ee/veganresource', 'https://github.com/eliperez-dev/UntilEveryCage']) expect(footer).toContain(url);
    expect(footer).toContain('AGPLv3 or later');
    expect(footer).toContain('CC BY-NC-SA where applicable');
    expect(footer).toContain('Counter Adapted from <a href="https://www.adaptt.org/" target="_blank" rel="noreferrer">ADAPTT</a>.');
    expect(footer).not.toContain('Counter approach adapted');
    expect(picker).toContain('new maplibregl.NavigationControl');
    expect(mapSurface).not.toContain('new maplibregl.NavigationControl');
    expect(mapSurface).not.toContain('Right-drag to rotate / Left-drag to pan');
    expect(footer).toContain('Final Nail');
    expect(footer).toContain('<div class="application-version-slot"><ApplicationVersion /></div>');
    expect(footer).not.toContain('v1.5.1');
  });

  it('keeps public community browsing tied to a published release, separately from intake', () => {
    expect(contribute).toContain("current('community')");
    expect(contribute).toContain('{#if communityReleasePublished}<a href={utilityHref(\'community\')}>Community submissions</a>{/if}');
    expect(contribute).toContain("Object.entries(taskNames)");
    expect(api).toContain("current('community')");
    expect(api).toContain('{#if communityReleaseAvailable}<option value="community">Community submissions</option>{/if}');
    expect(api).toContain('selectedReleaseId: selectedFromRoute');
    expect(api).toContain('repository.current(profile, controller.signal, chosenId)');
    expect(api).toContain('API release ID: <code>{releaseId}</code>');
    expect(api).not.toContain("limit: '1'");
  });

  it('keeps the map-selected historic release in API and download links', () => {
    const app = readFileSync(resolve(process.cwd(), 'src/app/App.svelte'), 'utf8');
    expect(app).toContain('selectedReleaseId={new URLSearchParams(route.returnMapHref?.split(\'?\')[1] ?? \'\').get(\'release_id\')}');
    expect(api).toContain("...(releaseId ? { release_id: releaseId } : {})");
    expect(api).toContain('aria-label="Public release"');
  });

  it('uses a private fragment tracking capability for status lookup', () => {
    expect(contributions).toContain('Track submission');
    expect(contributions).toContain('receipt_secret');
    expect(contributions).toContain('Open your private tracking link');
    expect(contributions).not.toContain('Lost receipts cannot be recovered');
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
