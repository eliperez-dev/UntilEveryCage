import { describe, expect, it } from 'vitest';
import { publicGraphConnections } from '../../src/fixtures/publicGraph';
import { graphConnectionSchema } from '../../src/api/publicGraphSchema';

describe('public graph fixture contract', () => {
  it('covers exact and every public inferred confidence band', () => {
    expect(publicGraphConnections.map(row => row.confidence_band)).toEqual(['exact', 'high', 'medium', 'low']);
    for (const row of publicGraphConnections) expect(graphConnectionSchema.safeParse(row).success).toBe(true);
  });
});
