import { describe, expect, it } from 'vitest';
import { maxUnpaintedBranchMs } from '../helpers/clusterVisualCoverage';

describe('painted cluster branch coverage', () => {
  const frame = (time: number, visible: string[]) => ({ time, visible, hidden: ['parent'] });
  it('detects a real blank interval instead of accepting a merely known descendant', () => {
    expect(maxUnpaintedBranchMs([frame(0, []), frame(600, [])], [['parent', 'child']])).toBe(600);
  });
  it('accepts a painted child while the replacement parent waits for pairing', () => {
    expect(maxUnpaintedBranchMs([frame(0, ['child']), frame(600, ['child'])], [['parent', 'child']])).toBe(0);
  });
  it('follows skipped levels and rejects artwork from an unrelated region', () => {
    const lineage: [string, string][] = [['parent', 'middle'], ['middle', 'child']];
    expect(maxUnpaintedBranchMs([frame(0, ['child']), frame(600, ['child'])], lineage)).toBe(0);
    expect(maxUnpaintedBranchMs([frame(0, ['unrelated']), frame(600, ['unrelated'])], lineage)).toBe(600);
  });
  it('resets the missing interval as soon as the parent or its branch paints', () => {
    expect(maxUnpaintedBranchMs([frame(0, []), frame(250, []), frame(300, ['parent']), frame(350, []), frame(500, [])], [])).toBe(250);
  });
});
