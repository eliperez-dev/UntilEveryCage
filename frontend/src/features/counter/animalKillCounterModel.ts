export const ANIMAL_KILL_COUNTER_MODEL = {
  basis: 'legacy-v1-annual-rates',
  yearLengthDays: 365,
  attribution: 'V1 page references Fishcount.org.uk, FAO, and estimates for lab-animal use and global meat trade.',
  limitation: 'These inherited annual rates have broad attributions, and some lack a traceable edition or year. They are estimates, not a complete or measured global total.',
} as const;

export const ANIMAL_KILL_GROUPS = [
  { id: 'fish', label: 'Fish', annualEstimate: 2_900_000_000_000, source: 'Fishcount.org.uk estimate' },
  { id: 'chickens', label: 'Chickens', annualEstimate: 74_000_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'ducks', label: 'Ducks', annualEstimate: 3_000_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'pigs', label: 'Pigs', annualEstimate: 1_500_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'rabbits', label: 'Rabbits', annualEstimate: 1_100_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'turkeys', label: 'Turkeys', annualEstimate: 670_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'geese', label: 'Geese', annualEstimate: 650_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'sheep', label: 'Sheep', annualEstimate: 570_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'goats', label: 'Goats', annualEstimate: 475_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'cows', label: 'Cows and calves', annualEstimate: 345_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'lab-rodents', label: 'Lab rodents', annualEstimate: 115_000_000, source: 'V1 labels this an estimate; source and year not specified' },
  { id: 'other-birds', label: 'Other birds', annualEstimate: 60_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'buffaloes', label: 'Buffaloes', annualEstimate: 25_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'dogs', label: 'Dogs', annualEstimate: 25_000_000, source: 'V1 labels this a global meat-trade estimate; source and year not specified' },
  { id: 'cats', label: 'Cats', annualEstimate: 4_000_000, source: 'V1 labels this a global meat-trade estimate; source and year not specified' },
  { id: 'horses', label: 'Horses', annualEstimate: 4_000_000, source: 'FAO, edition/year not retained in V1' },
  { id: 'donkeys', label: 'Donkeys', annualEstimate: 3_000_000, source: 'FAO, V1 grouped donkeys and mules; edition/year not retained' },
  { id: 'camels', label: 'Camels', annualEstimate: 2_000_000, source: 'FAO, edition/year not retained in V1' },
] as const;

export function estimateGroupSinceOpen(annualEstimate: number, elapsedMilliseconds: number): number {
  if (!Number.isFinite(elapsedMilliseconds) || elapsedMilliseconds <= 0) return 0;
  return Math.floor(annualEstimate * (elapsedMilliseconds / (ANIMAL_KILL_COUNTER_MODEL.yearLengthDays * 86_400_000)));
}
