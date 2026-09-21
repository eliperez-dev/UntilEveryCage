export type ScaleStep = Readonly<{
  id: string;
  label: string;
  multiplier: number;
  estimate: number;
  uncertainty: string;
}>;

// Synthetic interaction values only. They are intentionally not presented as
// an estimate of a country, company, facility, or real-world annual total.
// Keep this private/dev-only model separate from any sourced aggregate ledger.
export const SYNTHETIC_BASE = 1;

export const scaleSteps: readonly [ScaleStep, ...ScaleStep[]] = [
  { id: 'one', label: 'One individual', multiplier: 1, estimate: SYNTHETIC_BASE, uncertainty: 'Illustrative range: 1–1' },
  { id: 'small', label: 'A small group', multiplier: 10, estimate: SYNTHETIC_BASE * 10, uncertainty: 'Illustrative range: 8–12' },
  { id: 'large', label: 'A large group', multiplier: 100, estimate: SYNTHETIC_BASE * 100, uncertainty: 'Illustrative range: 80–120' },
  { id: 'system', label: 'A system-scale example', multiplier: 1000, estimate: SYNTHETIC_BASE * 1000, uncertainty: 'Illustrative range: 800–1,200' }
];

export const formatCount = (value: number): string => new Intl.NumberFormat('en-US').format(value);
