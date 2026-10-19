import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const component = readFileSync(resolve(process.cwd(), 'src/design-lab/components/MapSurface.svelte'), 'utf8');
const pinPicker = readFileSync(resolve(process.cwd(), 'src/app/ContributionPinPicker.svelte'), 'utf8');
const designLab = readFileSync(resolve(process.cwd(), 'src/design-lab/DesignLab.svelte'), 'utf8');
const field = readFileSync(resolve(process.cwd(), 'src/design-lab/variants/field/Field.svelte'), 'utf8');
const masthead = readFileSync(resolve(process.cwd(), 'src/app/PreviewMasthead.svelte'), 'utf8');

describe('real private preview map projection', () => {
  it('keeps the reviewed client-side Supercluster path active for private preview', () => {
    expect(component).toContain('const usingMvt = false;');
    expect(component).toContain('restoreNativeProjection(instance, visible');
    expect(component).toContain('filterTestReleaseMapCollection');
    expect(component).toContain('appliedNativeFilterSignature === signature');
    expect(component).toContain('hasRealPreviewMapLayers');
    expect(component).toContain('const sourceId = null;');
    expect(component).toContain('camera movement must never reload it');
  });

  it('keeps a rejected candidate envelope visible until an explicit cache-clear retry', () => {
    expect(component).toContain('let candidateValidationFailed = false;');
    expect(component).toContain('if (mode === "candidate-preview" && candidateValidationFailed) return;');
    expect(component).toContain('candidateValidationFailed = false;');
    expect(component).toContain('void loadNativeFeed();');
  });

  it('emits MapLibre workers through Vite worker URLs so sibling worker modules are retained', () => {
    expect(component).toContain('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url');
    expect(pinPicker).toContain('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url');
  });

  it('reacts to verified release metadata and forwards its manifest identity to the map feed', () => {
    expect(designLab).toContain("const publicReleaseId = writable<string | null>(null);");
    expect(designLab).toContain("const activePublicReleaseId = writable<string | null>(null);");
    expect(designLab).toContain("const dataStatus = writable<'loading' | 'ready' | 'empty' | 'error' | 'unauthorized'>('loading');");
    expect(designLab).toContain("$dataError = current ? '' : $pinnedPublicReleaseId ? 'Selected release unavailable.'");
    expect(designLab).toContain('...untrack(() => mapDiagnostics)');
    expect(designLab).toContain('Current verified release ${$activePublicReleaseId}');
    expect(designLab).toContain("'v0 verified archive'");
    expect(designLab).toContain("'Selected release unavailable.'");
    expect(field).toContain('selectedReleaseId={mode === "public-release" ? selectedPublicReleaseId : null}');
    expect(field).toContain('mode === "public-release" && dataStatus === "error"');
    expect(masthead).toContain('Selected release unavailable');
    expect(designLab).toContain('refreshPinnedPublicRelease?.();');
    expect(field).toContain('publicReleaseManifestIdentity = null,');
    expect(field).toContain('{publicReleaseManifestIdentity}');
  });
});
