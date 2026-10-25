import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const masthead = readFileSync(resolve(process.cwd(), 'src/app/PreviewMasthead.svelte'), 'utf8');
const help = readFileSync(resolve(process.cwd(), 'src/app/HelpPage.svelte'), 'utf8');
const contributions = readFileSync(resolve(process.cwd(), 'src/app/CommunityContributions.svelte'), 'utf8');
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

  it('uses written help instead of an embedded tutorial video', () => {
    expect(help).toContain('<h2>Contribute</h2>');
    expect(help).not.toContain('<video');
    expect(help).not.toContain('contribution-types.webm');
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
