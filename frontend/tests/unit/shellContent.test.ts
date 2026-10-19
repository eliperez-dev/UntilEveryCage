import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const masthead = readFileSync(resolve(process.cwd(), 'src/app/PreviewMasthead.svelte'), 'utf8');
const help = readFileSync(resolve(process.cwd(), 'src/app/HelpPage.svelte'), 'utf8');
const contributions = readFileSync(resolve(process.cwd(), 'src/app/CommunityContributions.svelte'), 'utf8');
const field = readFileSync(resolve(process.cwd(), 'src/design-lab/variants/field/Field.svelte'), 'utf8');
const atlas = readFileSync(resolve(process.cwd(), 'src/design-lab/variants/atlas/Atlas.svelte'), 'utf8');

describe('normal shell content', () => {
  it('keeps release context compact and removes unavailable account controls', () => {
    expect(masthead).toContain('Release details');
    expect(masthead).toContain('text-overflow:ellipsis');
    expect(masthead).not.toContain('Account unavailable');
    expect(masthead).not.toContain('Preview release');
  });

  it('uses written help instead of an embedded tutorial video', () => {
    expect(help).toContain('<h2>Contribute</h2>');
    expect(help).not.toContain('<video');
    expect(help).not.toContain('contribution-types.webm');
  });

  it('uses a private bearer receipt for status lookup without repeated loss warnings', () => {
    expect(contributions).toContain('private receipt authorizes the lookup');
    expect(contributions).toContain('Enter the Submission ID and private receipt');
    expect(contributions).not.toContain('Lost receipts cannot be recovered');
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
