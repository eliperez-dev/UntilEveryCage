import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const component = readFileSync(resolve(process.cwd(), 'src/design-lab/components/MapSurface.svelte'), 'utf8');

describe('real private preview map projection', () => {
  it('keeps the reviewed client-side Supercluster path active for private preview', () => {
    expect(component).toContain('const usingMvt = false;');
    expect(component).toContain('addRealPreviewMapLayers(instance, visible');
    expect(component).toContain('filteredNativeCollection(nativeFullCollection, sourceId)');
    expect(component).toContain('if (appliedNativeSourceId === sourceId) return;');
    expect(component).toContain('const sourceId = null;');
    expect(component).toContain('camera movement must never reload it');
  });

  it('keeps a rejected candidate envelope visible until an explicit cache-clear retry', () => {
    expect(component).toContain('let candidateValidationFailed = false;');
    expect(component).toContain('if (mode === "candidate-preview" && candidateValidationFailed) return;');
    expect(component).toContain('candidateValidationFailed = false;');
    expect(component).toContain('void loadNativeFeed();');
  });
});
