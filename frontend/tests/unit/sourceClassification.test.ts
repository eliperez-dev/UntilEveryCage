import { describe, expect, it } from 'vitest';
import { sourceClassificationLabels } from '../../src/features/locations/sourceClassification';

describe('source classification presentation', () => {
  it('does not append a class code already included as a complete phrase in its label', () => {
    expect(sourceClassificationLabels([], [{ sourceLabel: 'Class H Intermediate Handler', sourceCode: 'Class H' }], [])).toEqual(['Class H Intermediate Handler']);
    expect(sourceClassificationLabels([], [{ sourceLabel: 'Class HC handler', sourceCode: 'Class H' }], [])).toEqual(['Class HC handler (Class H)']);
  });
  it('omits source terms already stated as activities but preserves distinct codes and labels', () => {
    expect(sourceClassificationLabels(
      ['NRTE Chicken Processing', 'Poultry Processing'],
      [
        { sourceLabel: 'Poultry processing', sourceCode: 'CH-NRTE' },
        { sourceLabel: 'Establishment type 3', sourceCode: 'FSIS-03' },
      ],
      ['NRTE chicken processing', 'Chicken', 'Poultry processing'],
    )).toEqual(['CH NRTE', 'Establishment type 3 (FSIS 03)']);
  });

  it('keeps aliases distinct from displayed activity facts and collapses duplicate terms', () => {
    expect(sourceClassificationLabels(
      ['Poultry establishment', 'Poultry establishment'],
      [{ sourceLabel: 'Former source alias', sourceCode: 'Poultry establishment' }],
      ['Chicken processing'],
    )).toEqual(['Poultry establishment', 'Former source alias']);
  });

  it('deduplicates semicolon-separated source terms individually without splitting commas', () => {
    expect(sourceClassificationLabels(
      ['Cutting; freezing; processing; United States, poultry division'],
      [],
      ['Cutting', 'Freezing', 'Processing'],
    )).toEqual(['United States, poultry division']);
  });
});
