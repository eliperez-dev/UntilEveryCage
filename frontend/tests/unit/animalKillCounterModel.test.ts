import { describe, expect, it } from 'vitest';
import { ANIMAL_KILL_COUNTER_MODEL, ANIMAL_KILL_GROUPS, estimateGroupSinceOpen } from '../../src/features/counter/animalKillCounterModel';

describe('legacy animal kill counter model', () => {
  it('retains the 18 V1 groups and records source limitations', () => {
    expect(ANIMAL_KILL_GROUPS).toHaveLength(18);
    expect(ANIMAL_KILL_GROUPS[0]).toMatchObject({ id: 'fish', annualEstimate: 2_900_000_000_000 });
    expect(ANIMAL_KILL_GROUPS.find(group => group.id === 'lab-rodents')?.source).toContain('not specified');
    expect(ANIMAL_KILL_COUNTER_MODEL.basis).toBe('legacy-v1-annual-rates');
    expect(ANIMAL_KILL_COUNTER_MODEL.limitation).toContain('not a complete or measured global total');
  });

  it('uses elapsed time over a 365-day year without accumulating timer ticks', () => {
    expect(estimateGroupSinceOpen(365, 86_400_000)).toBe(1);
    expect(estimateGroupSinceOpen(365, 43_200_000)).toBe(0);
    expect(estimateGroupSinceOpen(365, Number.NaN)).toBe(0);
  });
});
