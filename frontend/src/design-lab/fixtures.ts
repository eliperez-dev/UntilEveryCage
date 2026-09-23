import type { LabRecord, Precision } from './contract';

const places = [
  ['Denmark','Aarhus',56.1629,10.2039], ['France','Lyon',45.764,4.8357],
  ['Italy','Parma',44.8015,10.3279], ['United States','Des Moines',41.5868,-93.625],
  ['Australia','Geelong',-38.1499,144.3617], ['Germany','Oldenburg',53.1435,8.2146],
] as const;
const categories = ['Poultry', 'Pig', 'Dairy', 'Processing', 'Laboratory', 'Aquaculture'] as const;
const precisions: readonly Precision[] = ['exact', 'city', 'coarse', 'unmapped'];

export const LAB_SENTINEL = 'F1A_SYNTHETIC_REVIEW_ONLY';
export const labRecords: readonly LabRecord[] = Object.freeze(Array.from({ length: 96 }, (_, index) => {
  const place = places[index % places.length]!;
  const precision = precisions[index % precisions.length]!;
  const dense = index < 24;
  const offset = dense ? (index % 6) * .025 : ((index * 17) % 29 - 14) * .32;
  return Object.freeze({
    id: `syn-${String(index + 1).padStart(3, '0')}`,
    name: `Synthetic ${categories[index % categories.length]} record ${String(index + 1).padStart(2, '0')}`,
    category: categories[index % categories.length]!, country: place[0], locality: place[1], precision,
    latitude: precision === 'unmapped' ? null : place[2] + offset,
    longitude: precision === 'unmapped' ? null : place[3] + offset * 1.4,
  });
}));
