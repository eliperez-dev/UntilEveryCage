import { describe, expect, it } from 'vitest';
import { publicGraphConnections } from '../../src/fixtures/publicGraph';
import { graphConnectionSchema } from '../../src/api/publicGraphSchema';

describe('public graph fixture contract', () => {
  it('covers exact and every public inferred confidence band', () => {
    expect(publicGraphConnections.map(row => row.confidence_band)).toEqual(['exact', 'high', 'medium', 'low']);
    for (const row of publicGraphConnections) expect(graphConnectionSchema.safeParse(row).success).toBe(true);
  });

  it('accepts a selected-release safe endpoint label while keeping it optional for older responses', () => {
    const edge = publicGraphConnections[0];
    expect(graphConnectionSchema.safeParse(edge).success).toBe(true);
    expect(graphConnectionSchema.safeParse({
      ...edge,
      to: { ...edge.to, display_name: 'Source-supported organization name' },
    }).success).toBe(true);
  });
});
