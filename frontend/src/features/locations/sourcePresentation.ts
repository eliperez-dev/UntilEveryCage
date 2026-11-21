export function sourceDisplayName(id: string, label?: string): string {
  // The published ICPE snapshot may supply its identifier as the display name.
  if (id === 'fr.georisques.icpe.animal' && (!label || label === id)) {
    return 'Géorisques ICPE — Animal facilities';
  }
  return label ?? id;
}
