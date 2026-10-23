import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const component = readFileSync(resolve(process.cwd(), 'src/app/RecordConnections.svelte'), 'utf8');

describe('public record connections', () => {
  it('pins requests and linked facility records to the selected release and profile', () => {
    expect(component).toContain('release_id: releaseId');
    expect(component).toContain('graph.neighborhood(facilityId, profile, filters(');
    expect(component).toContain('facilityId: id, profile, releaseId');
    expect(component).toContain("kind: 'record', facilityId: id, profile, releaseId");
  });

  it('uses only the API-approved organization display name and never resolves its identifier as a facility', () => {
    expect(component).toContain("if (endpoint.entity_type === 'organization') return endpoint.display_name ?? 'Organization'");
    expect(component).toContain("other.entity_type === 'facility' && other.entity_id");
    expect(component).not.toContain('source_identifier');
  });

  it('presents exact and inferred semantics with expandable source and method details', () => {
    expect(component).toContain('Exact · source-supported');
    expect(component).toContain('Inferred');
    expect(component).toContain('Method and evidence');
    expect(component).toContain('edge.provenance.source_ids');
    expect(component).toContain('Object.keys(edge.signals)');
    expect(component).toContain('edge.disclaimer');
    expect(component).toContain('No connections in this release.');
  });
});
