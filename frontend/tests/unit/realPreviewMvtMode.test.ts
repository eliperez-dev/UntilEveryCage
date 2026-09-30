import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const component = readFileSync(resolve(process.cwd(), 'src/design-lab/components/MapSurface.svelte'), 'utf8');

describe('real private preview map projection', () => {
  it('uses snapshot-keyed server MVT tiles only for the explicitly selected real-preview mode', () => {
    expect(component).toContain('const usingMvt = mode === "real-preview";');
    expect(component).toContain('url.pathname.includes("/dev/real-preview/map/tiles/")');
    expect(component).toContain('addMvtLocationLayers(map, mapState.sourceId ?? undefined)');
  });
});
