import { describe, expect, it } from 'vitest';
import type { TaxonomyClassification } from '../../src/domain/taxonomy';
import { affirmativeSourceEntries, classificationSummary, recordCategoryIdentity } from '../../src/features/locations/classificationSummary';

const taxonomy = (overrides: Partial<TaxonomyClassification> = {}): TaxonomyClassification => ({
  displayCategory: 'other_regulated_premises', primaryCategories: ['other_regulated_premises'],
  leafActivities: [{ key: 'general_food_business', label: 'General food business' }], assignments: [], taxonomyVersion: 'uec-taxonomy-v1', ...overrides,
});

describe('record classification overview', () => {
  it('explains APHIS H registration without turning a fallback food classification into an activity', () => {
    const result = classificationSummary({ sourceId: 'us.aphis', taxonomy: taxonomy(), sourceFacts: { nativeActivityLabel: 'Class H Intermediate Handler', nativeActivityCode: 'Class H' } });
    expect(result.summary).toBe('APHIS registration: Intermediate handler (Class H).');
    expect(result.activities).toEqual([]);
    expect(result.supportingActivities).toEqual(['General food business']);
    expect(result.sourceLabels).toEqual(['Class H Intermediate Handler']);
  });

  it('does not infer APHIS meanings from another source or hide that source’s food activity', () => {
    const result = classificationSummary({ sourceId: 'example.registry', taxonomy: taxonomy(), sourceFacts: { nativeActivityCode: 'Class H' } });
    expect(result.summary).toBe('Recorded activities: General food business.');
    expect(result.sourceLabels).toEqual(['Class H']);
  });

  it('keeps a native class code once when the complete code is already in its fuller source label', () => {
    const result = classificationSummary({ sourceId: 'us.aphis', sourceFacts: { nativeActivityLabel: 'Class T - Carrier', nativeActivityCode: 'Class T' } });
    expect(result.sourceLabels).toEqual(['Class T - Carrier']);
    const distinct = classificationSummary({ sourceFacts: { nativeActivityLabel: 'Class TH - Synthetic', nativeActivityCode: 'Class T' } });
    expect(distinct.sourceLabels).toEqual(['Class TH - Synthetic', 'Class T']);
  });

  it('bounds the summary while retaining all positive details and excluding boolean and textual negatives', () => {
    const result = classificationSummary({ sourceFacts: { processingActivities: {
      cutting: true, freezing: 'Yes', packing: '1', smoking: 'Y', rejected: false, absent: 'No', none: '0', blank: '', not_active: 'false', negative: 'N',
    } } });
    expect(result.summary).toBe('Recorded activities: Cutting, Freezing, Packing, …');
    expect(result.activities).toEqual(['Cutting', 'Freezing', 'Packing', 'Smoking']);
    expect(affirmativeSourceEntries({ animals: 'RTE', no: 'false' })).toEqual([['animals', 'RTE']]);
  });

  it('keeps extra processing facts alongside an APHIS registration and retains exact source identifiers', () => {
    const result = classificationSummary({ sourceId: 'us.aphis', taxonomy: taxonomy(), sourceFacts: { nativeActivityCode: 'Class H', nativeActivityLabel: 'Source-code_01', processingActivities: { cutting: true } } });
    expect(result.activities).toEqual(['Cutting']);
    expect(result.sourceLabels).toContain('Source-code_01');
    expect(result.summary).not.toContain('Cutting');
  });

  it('does not invent activities or taxonomy when no details exist', () => {
    expect(classificationSummary({})).toEqual({ summary: '', categories: ['Unclassified'], activities: [], sourceLabels: [], supportingActivities: [], hasAphisClassification: false });
    expect(recordCategoryIdentity({}).pinFile).toBe('marker-icon-2x-grey.png');
  });

  it('uses neutral APHIS classification wording for licenses, courtesy types, and mixed classes', () => {
    for (const nativeActivityCode of ['Class A', 'Class B', 'Class C', 'Class F', 'Class G', 'Class V', 'Class H; Class C']) {
      const result = classificationSummary({ sourceId: 'us.aphis', sourceFacts: { nativeActivityCode } });
      expect(result.summary.startsWith('APHIS classification:')).toBe(true);
      expect(result.summary).not.toContain('registration');
    }
    expect(classificationSummary({ sourceId: 'us.aphis', sourceFacts: { nativeActivityCode: 'Class R; Class H; Class T' } }).summary.startsWith('APHIS registration:')).toBe(true);
  });

  it('bounds unusually long generated summaries without losing the supporting activity', () => {
    const label = 'Synthetic activity '.repeat(30).trim();
    const result = classificationSummary({ taxonomy: taxonomy({ leafActivities: [{ key: 'synthetic', label }] }) });
    expect(result.summary.length).toBeLessThanOrEqual(220);
    expect(result.summary.endsWith('…')).toBe(true);
    expect(result.supportingActivities).toEqual([label]);
  });

  it('uses specific processing activities in the overview while retaining the generic leaf in detail', () => {
    const result = classificationSummary({ taxonomy: taxonomy({ primaryCategories: ['processing_and_preparation'], leafActivities: [{ key: 'processing', label: 'Processing' }] }), sourceFacts: { processingActivities: { nrte_chicken_processing: true, meat_cutting: true } } });
    expect(result.summary).toBe('Recorded activities: Meat cutting, NRTE chicken processing.');
    expect(result.activities).toEqual(['Meat cutting', 'NRTE chicken processing']);
    expect(result.supportingActivities).toEqual(['Processing', 'Meat cutting', 'NRTE chicken processing']);
    expect(classificationSummary({ taxonomy: taxonomy({ primaryCategories: ['processing_and_preparation'], leafActivities: [{ key: 'processing', label: 'Processing' }] }) }).activities).toEqual(['Processing']);
  });

  it('uses the map’s priority and original pin family for multiple categories and legacy keys', () => {
    const record = { category: 'animal_keeping_and_production', taxonomy: taxonomy({ primaryCategories: ['animal_keeping_and_production', 'processing_and_preparation', 'slaughter'] }) };
    expect(recordCategoryIdentity(record)).toEqual({ key: 'slaughter', label: 'Slaughter', pinFile: 'marker-icon-2x-red.png' });
    expect(recordCategoryIdentity({ category: 'processing' }).pinFile).toBe('marker-icon-2x-blue.png');
    expect(classificationSummary(record).categories).toEqual(['Animal keeping and production', 'Processing and preparation', 'Slaughter']);
  });

  it('localizes generated templates without translating original source text', () => {
    const result = classificationSummary({ sourceId: 'us.aphis', sourceFacts: { nativeActivityLabel: 'Class H Intermediate Handler' } }, label => ({ 'APHIS registration': 'Registro APHIS', 'Intermediate handler': 'Intermediario', Class: 'Clase' })[label] ?? label);
    expect(result.summary).toBe('Registro APHIS: Intermediario (Clase H).');
    expect(result.sourceLabels).toEqual(['Class H Intermediate Handler']);
  });
});
