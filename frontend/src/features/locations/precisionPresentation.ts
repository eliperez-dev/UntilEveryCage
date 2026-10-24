const labels: Readonly<Record<string, string>> = Object.freeze({
  exact: 'Exact public point',
  source_reported: 'Source-provided coordinates',
  approximate: 'Approximate location',
  city: 'City-level approximation',
  provider_locality_approximate: 'City-level approximation',
  coarse: 'Coarse area approximation',
  unmapped: 'Unmapped · no public point',
});

export function precisionPresentation(value: string | null | undefined): string {
  return value ? labels[value] ?? 'Location precision unavailable' : 'Location precision unavailable';
}
