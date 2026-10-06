const labels: Readonly<Record<string, string>> = Object.freeze({
  exact: 'Exact public point',
  source_reported: 'Source-reported coordinate · precision not independently verified',
  approximate: 'Approximate public location · not an exact facility point',
  city: 'City-level approximation',
  coarse: 'Coarse area approximation',
  unmapped: 'Unmapped · no public point',
});

export function precisionPresentation(value: string | null | undefined): string {
  return value ? labels[value] ?? 'Location precision unavailable' : 'Location precision unavailable';
}
