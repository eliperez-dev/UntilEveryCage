import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const component = readFileSync(resolve(process.cwd(), 'src/app/RecordConnections.svelte'), 'utf8');
const aphisReports = readFileSync(resolve(process.cwd(), 'src/app/AphisReports.svelte'), 'utf8');

describe('public record connections', () => {
  it('pins requests and linked facility records to the selected release and profile', () => {
    expect(component).toContain('release_id: releaseId');
    expect(component).toContain('graph.neighborhood(facilityId, profile, filters(');
    expect(component).toContain('facilityId: id, profile, releaseId');
    expect(component).toContain("kind: 'record', facilityId: id, profile, releaseId");
  });

  it('uses only the API-approved organization display name and never resolves its identifier as a facility', () => {
    expect(component).toContain("if (endpoint.entity_type === 'organization') return endpoint.display_name ?? tr('Organization', $language)");
    expect(component).toContain("other.entity_type === 'facility' && other.entity_id");
    expect(component).not.toContain('source_identifier');
  });

  it('presents exact and inferred semantics with expandable source and method details', () => {
    expect(component).toContain('Exact source');
    expect(component).toContain("${tr('Inferred', $language)} · ${tr(humanize(edge.confidence_band), $language)} ${tr('confidence', $language)}");
    expect(component).not.toContain('Exact · source-supported');
    expect(component).toContain('Method and evidence');
    expect(component).toContain('edge.provenance.source_ids');
    expect(component).toContain('Object.keys(edge.signals)');
    expect(component).not.toContain('edge.disclaimer');
    expect(component).toContain('<p class="empty">{tr(\'None\', $language)}</p>');
  });

  it('shows None without filters for an empty record, while keeping active filters available', () => {
    expect(component).toContain("kind !== 'all' || confidence !== 'all' || (!loading && !error && rows.length > 0)");
    expect(component).toContain('<p class="empty">{tr(\'None\', $language)}</p>');
    expect(component).toContain("tr('Loading connections…', $language)");
  });

  it('delegates relevance-gated APHIS reports to the on-demand report component without generic copy', () => {
    expect(component).toContain("import AphisReports from './AphisReports.svelte'");
    expect(component).toContain('<AphisReports {facilityId} {releaseId} {profile} {sourceId} {sourceFacts} />');
    expect(aphisReports).toContain('isAphisRelevant(sourceId, sourceFacts)');
    expect(aphisReports).toContain('onclick={() => void load(kind)}');
    expect(aphisReports).toContain("tr('Loading reports…', $language)");
    expect(aphisReports).toContain("tr('Reports could not be loaded.', $language)");
    expect(aphisReports).toContain('Open APHIS source page');
    expect(aphisReports).not.toContain('publication gates');
    expect(aphisReports).not.toContain('No APHIS evidence references are approved');
  });

  it('offers explicit annual and inspection fetches and prevents duplicate or stale requests', () => {
    expect(aphisReports).toContain("kind === 'annual_reports' ? 'Fetch annual reports' : 'Fetch inspection reports'");
    expect(aphisReports).toContain("tr(selected === 'annual_reports' ? 'No annual reports found.' : 'No inspection reports found.', $language)");
    expect(aphisReports).toContain('if (loading) return;');
    expect(aphisReports).toContain('if (selected === kind && !next && !error && fetched) return;');
    expect(aphisReports).toContain('const queryKey = $derived(`${facilityId}\\u0000${releaseId}\\u0000${profile}`)');
    expect(aphisReports).toContain('request !== version');
    expect(aphisReports).toContain('page.releaseId !== releaseId');
    expect(aphisReports).toContain('onclick={() => void load(selected!, retryCursor ?? undefined)}');
    expect(aphisReports).toContain('fetched = false;');
  });
});
