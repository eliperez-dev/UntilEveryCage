import { describe, expect, it } from 'vitest';
import type { AphisAnnualReport, DerivedSourceVolumeRange } from '../../src/domain/location';
import type { TaxonomyClassification, TaxonomyPrimaryKey } from '../../src/domain/taxonomy';
import { CLASSIFICATION_EXPLANATIONS, classificationExplanation } from '../../src/features/locations/classificationExplanation';
import { classificationSummary } from '../../src/features/locations/classificationSummary';

const taxonomy = (primary: TaxonomyPrimaryKey, leaves: string[] = []): TaxonomyClassification => ({ displayCategory:primary,primaryCategories:[primary],leafActivities:leaves.map(key=>({key,label:key})),assignments:[],taxonomyVersion:'uec-taxonomy-v1' });
const report = (fiscalYear = '2025', counts = [18, 0, 7]): AphisAnnualReport => ({ fiscalYear,speciesCounts:counts.map((count,index)=>({species:`Synthetic species ${index}`,count})),sourceUrl:'https://example.test/annual-report',safeProvenance:{sourceId:'us.aphis.annual-reports',evidenceType:'annual_reports',matchMethod:'exact_source_identifier',matchedIdentifierTypes:['certificate_number']} });

describe('classification explanations', () => {
  it('covers every broad category with a bounded definition and source references', () => {
    for(const category of ['animal_keeping_and_production','slaughter','processing_and_preparation','research_and_animal_use','other_regulated_premises','unclassified'] as const) {
      const result = classificationExplanation({category});
      expect(result.keys).toEqual([category]);
      expect(result.text.split(/\.\s|\.$/).filter(Boolean)).toHaveLength(1);
      expect(result.references.length).toBeGreaterThan(0);
    }
    expect(Object.keys(CLASSIFICATION_EXPLANATIONS).length).toBe(41);
  });

  it('explains exact APHIS classes without turning carriers into laboratory-only transport', () => {
    for(const code of ['A','B','C','F','H','R','T']) expect(classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:`Class ${code}`}}).keys).toEqual([`aphis_${code.toLowerCase()}`]);
    const carrier = classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class T'}});
    expect(carrier.text).toContain('transport regulated animals for hire');
    expect(carrier.text).not.toMatch(/laborator|research|this facility/i);
    expect(classificationExplanation({sourceId:'another.registry',category:'other_regulated_premises',sourceFacts:{nativeActivityLabel:'Class T - Carrier'}}).keys).toEqual(['other_regulated_premises']);
    expect(classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityLabel:'Class TH synthetic'}}).keys).toEqual(['unclassified']);
  });

  it('requires the full source-native designation for legacy G and V definitions', () => {
    for(const code of ['G','V']) expect(classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:`Class ${code}`}}).keys).toEqual(['research']);
    expect(classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityLabel:'Class G - Agricultural Research Facility ARS'}}).keys).toEqual(['aphis_g']);
    expect(classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityLabel:"Class V - Veteran's Administration Hospital"}}).keys).toEqual(['aphis_v']);
  });

  it('bounds mixed classes to two explanations and preserves every original term in detail', () => {
    const record = {sourceId:'us.aphis',sourceFacts:{nativeActivityLabel:'Class T - Carrier; Class H - Intermediate Handler; Class R - Research Facility'}};
    const result = classificationExplanation(record);
    expect(result.keys).toEqual(['aphis_r','aphis_h']);
    expect(result.text.split(/\.\s|\.$/).filter(Boolean)).toHaveLength(2);
    expect(classificationSummary(record).sourceLabels).toEqual(['Class T - Carrier','Class H - Intermediate Handler','Class R - Research Facility']);
  });

  it('uses specific recognised activities before a broad fallback and ignores invented lookalikes', () => {
    for(const key of ['meat_processing','fish_processing','dairy_processing','egg_processing','cutting','mixed_food_processing']) expect(classificationExplanation({taxonomy:taxonomy('processing_and_preparation',['processing',key])}).keys).toEqual([key]);
    expect(classificationExplanation({taxonomy:taxonomy('processing_and_preparation',['not_really_dairy_processing'])}).keys).toEqual(['processing_and_preparation']);
    expect(classificationExplanation({taxonomy:taxonomy('slaughter',['dairy_processing'])}).keys).toEqual(['slaughter']);
  });

  it('uses affirmative structured slaughter flags, without inferring a particular killing method', () => {
    const sourceFacts={speciesSlaughtered:{young_chicken_slaughter:'Yes',beef_cow_slaughter:'No',duck_slaughter:false}};
    const result=classificationExplanation({category:'slaughter',sourceFacts});
    expect(result.keys).toEqual(['poultry_slaughter']);
    expect(result.text).toContain('Typical stages include bleeding, removing feathers and removing internal organs.');
    expect(result.text.split(/\.\s|\.$/).filter(Boolean)).toHaveLength(2);
    expect(result.references[0]?.href).toBe('https://www.gov.uk/government/publications/legal-requirements-for-meat-establishments');
    expect(result.text).not.toMatch(/stunn|gas|electric|this facility/i);
    expect(classificationExplanation({category:'slaughter',sourceFacts:{speciesSlaughtered:{young_chicken_slaughter:'unknown'}}}).keys).toEqual(['slaughter']);
    expect(classificationExplanation({category:'slaughter',sourceFacts:{speciesSlaughtered:{beef_cow_slaughter:true}}}).keys).toEqual(['meat_slaughter']);
    expect(classificationExplanation({category:'slaughter',sourceFacts:{speciesSlaughtered:{beef_cow_slaughter:true,young_chicken_slaughter:true}}}).keys).toEqual(['slaughter']);
  });

  it('does not turn negative or unknown processing flags into an activity', () => {
    const record={category:'processing_and_preparation',sourceFacts:{processingActivities:{poultry_processing:'unknown',meat_cutting:'false'}}};
    expect(classificationExplanation(record).keys).toEqual(['processing_and_preparation']);
    expect(classificationExplanation({...record,sourceFacts:{processingActivities:{poultry_processing:'Y'}}}).keys).toEqual(['poultry_processing']);
  });

  it('keeps source-code meanings scoped to the documented source', () => {
    const base=taxonomy('other_regulated_premises');
    const assignments=[{primaryKey:'other_regulated_premises',leafKey:'logistics_and_storage',leafLabel:'Storage',sourceCodeReference:null,sourceLabelReference:null,sourceCode:'CS',sourceLabel:'Cold store',method:'direct',status:'mapped',taxonomyVersion:'uec-taxonomy-v1',crosswalkVersion:null,rulesetVersion:null,observationId:null,sourceRecordId:null,artifactId:null}] as const;
    expect(classificationExplanation({sourceId:'de.locations',taxonomy:{...base,assignments}}).keys).toEqual(['cold_store']);
    expect(classificationExplanation({sourceId:'another.registry',taxonomy:{...base,assignments}}).keys).toEqual(['other_regulated_premises']);
    expect(classificationExplanation({sourceId:'no.fiskeridir.aquaculture',category:'animal_keeping_and_production'}).keys).toEqual(['aquaculture']);
    expect(classificationExplanation({sourceId:'another.aquaculture',category:'animal_keeping_and_production'}).keys).toEqual(['animal_keeping_and_production']);
  });

  it('adds an exact latest-year reported total without calling it deaths or an annual estimate', () => {
    const record={sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class R',aphisAnnualReports:[report('2024',[999]),report('2025',[18,0,7])]}};
    const result=classificationExplanation(record);
    expect(result.text).toContain('The fiscal year 2025 report lists 25 animals across the reported species.');
    expect(result.text).not.toMatch(/dead|died|kill|estimated|360/);
    expect(result.references.at(-1)?.href).toBe('https://example.test/annual-report');
    expect(classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class R',aphisAnnualReports:[report('2025',[0])]}}).text).toContain('lists 0 animals');
  });

  it('omits ambiguous, invalid or unsafe report totals and preserves a two-sentence limit', () => {
    for(const aphisAnnualReports of [[report(),report()],[report('2025',[-1])],[report('2025',[Number.MAX_SAFE_INTEGER,1])],[report('2025',[1.5])]]) {
      const result=classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class R',aphisAnnualReports}});
      expect(result.text).not.toContain('report lists');
    }
    const result=classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class R; Class T',aphisAnnualReports:[report()]}});
    expect(result.text).not.toContain('report lists');
  });

  it('never annualises or duplicates verified 360-day slaughter ranges in the definition', () => {
    const range:DerivedSourceVolumeRange={ordinalCode:'test',lower:10,upper:20,bounds:'inclusive_lower_exclusive_upper',unit:'head',period:'trailing_360_days',methodVersion:'fsis-mpi-volume-codebook-2026-03-24-v1',sourceCodebookUrl:'https://example.test/codebook',verificationState:'source_codebook_verified'};
    const before=JSON.stringify(range);
    const result=classificationExplanation({category:'slaughter',sourceFacts:{derivedSourceVolumeRanges:[range]}});
    expect(result.text).toBe(CLASSIFICATION_EXPLANATIONS.slaughter.text);
    expect(JSON.stringify(range)).toBe(before);
  });

  it('localizes complete narrative templates and count placeholders', () => {
    const result=classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class R',aphisAnnualReports:[report('2025',[1200])] }},text=>text==='The fiscal year {year} report lists {count} animals across the reported species.'?'Rapport {year} : {count} animaux.':`Traduit: ${text}`,'fr');
    expect(result.text).toContain('Traduit: APHIS');
    expect(result.text).toMatch(/Rapport 2025 : 1.200 animaux\./);
  });
});
