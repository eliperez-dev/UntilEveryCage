import { describe, expect, it } from 'vitest';
import { selectLineageChildren } from '../../src/design-lab/components/mvtLineage';

describe('MVT lineage decisions', () => {
  it('selects only immediate children of the clicked parent and caps fanout', () => {
    const clusters = [
      { featureKey: 'one', parentKey: 'parent' },
      { featureKey: 'two', parentKey: 'parent' },
      { featureKey: 'other', parentKey: 'other-parent' },
    ];

    expect(selectLineageChildren(clusters, 'parent')).toEqual(clusters.slice(0, 2));
  });
});
