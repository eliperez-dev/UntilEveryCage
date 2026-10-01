import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const component = readFileSync(resolve(process.cwd(), 'src/design-lab/components/MapSurface.svelte'), 'utf8');

describe('real private preview map projection', () => {
  it('keeps the reviewed client-side Supercluster path active for private preview', () => {
    expect(component).toContain('const usingMvt = false;');
    expect(component).toContain('addRealPreviewMapLayers(instance, result.collection');
    expect(component).toContain('camera movement must never reload it');
  });
});
