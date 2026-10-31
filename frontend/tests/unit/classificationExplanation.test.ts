import { describe, expect, it } from 'vitest';
import type { AphisAnnualReport, DerivedSourceVolumeRange } from '../../src/domain/location';
import type { TaxonomyAssignment, TaxonomyClassification, TaxonomyPrimaryKey } from '../../src/domain/taxonomy';
import { CLASSIFICATION_EXPLANATIONS, classificationExplanation } from '../../src/features/locations/classificationExplanation';
import { classificationSummary } from '../../src/features/locations/classificationSummary';
import { es } from '../../src/app/locales/es';
import fr from '../../src/app/locales/fr';
import de from '../../src/app/locales/de';
import nl from '../../src/app/locales/nl';
import da from '../../src/app/locales/da';
import zhHans from '../../src/app/locales/zh-Hans';

const taxonomy = (primary: TaxonomyPrimaryKey, leaves: string[] = []): TaxonomyClassification => ({ displayCategory:primary,primaryCategories:[primary],leafActivities:leaves.map(key=>({key,label:key})),assignments:[],taxonomyVersion:'uec-taxonomy-v1' });
const report = (fiscalYear = '2025', counts = [18, 0, 7]): AphisAnnualReport => ({ fiscalYear,speciesCounts:counts.map((count,index)=>({species:`Synthetic species ${index}`,count})),sourceUrl:'https://example.test/annual-report',safeProvenance:{sourceId:'us.aphis.annual-reports',evidenceType:'annual_reports',matchMethod:'exact_source_identifier',matchedIdentifierTypes:['certificate_number']} });
const assignment = (leafKey: string, status: TaxonomyAssignment['status'] = 'mapped', primaryKey: TaxonomyPrimaryKey = 'processing_and_preparation'): TaxonomyAssignment => ({primaryKey,leafKey,leafLabel:leafKey,sourceCodeReference:null,sourceLabelReference:null,sourceCode:null,sourceLabel:null,method:'direct',status,taxonomyVersion:'uec-taxonomy-v1',crosswalkVersion:null,rulesetVersion:null,observationId:null,sourceRecordId:null,artifactId:null});
const namedReport = (speciesCounts: AphisAnnualReport['speciesCounts']): AphisAnnualReport => ({...report(),speciesCounts});

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
    expect(result.text).toContain('The source lists slaughter of chickens.');
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
    expect(classificationExplanation({sourceId:'another.registry',taxonomy:{...base,assignments}}).keys).toEqual(['logistics_and_storage']);
    expect(classificationExplanation({sourceId:'another.registry',taxonomy:{...base,assignments:[{...assignments[0],leafKey:null}]}}).keys).toEqual(['other_regulated_premises']);
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

  it('omits ambiguous, invalid or unsafe report totals and allows a dated fact for mixed research classes', () => {
    for(const aphisAnnualReports of [[report(),report()],[report('2025',[-1])],[report('2025',[Number.MAX_SAFE_INTEGER,1])],[report('2025',[1.5])]]) {
      const result=classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class R',aphisAnnualReports}});
      expect(result.text).not.toContain('report lists');
    }
    const result=classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class R; Class T',aphisAnnualReports:[report()]}});
    expect(result.text).toContain('The fiscal year 2025 report lists 25 animals');
    expect(result.text.split(/\.\s|\.$/).filter(Boolean)).toHaveLength(3);
  });

  it('combines named slaughter species and processing products without repeating the category', () => {
    const record={category:'slaughter',sourceFacts:{speciesSlaughtered:{beef_cow_slaughter:'Yes',steer_slaughter:true,young_chicken_slaughter:'y',duck_slaughter:'unknown'},processingActivities:{raw_intact_beef_processing:'1',rte_chicken_processing:true,meat_processing:true}}};
    const before=JSON.stringify(record);
    const result=classificationExplanation(record);
    expect(result.text).toBe('Slaughterhouses are places where animals are killed for meat. The source lists slaughter of cattle and chickens and processing of beef and chicken meat.');
    expect(result.text.split(/\.\s|\.$/).filter(Boolean)).toHaveLength(2);
    expect(JSON.stringify(record)).toBe(before);
  });

  it('names supported processing products without treating processing flags or volumes as deaths', () => {
    const result=classificationExplanation({category:'processing_and_preparation',sourceFacts:{processingActivities:{raw_non_intact_pork_processing:'TRUE',rte_chicken_processing:'yes',fish_processing:false,raw_intact_beef_processing:'unknown',fictional_cow_processing:true},speciesSlaughtered:{cattle:'No'}}});
    expect(result.text).toContain('The source lists processing of pork and chicken meat.');
    expect(result.text).not.toMatch(/slaughter|killed|deaths|beef|fish|fictional|cow/);
    expect(classificationExplanation({category:'processing_and_preparation',sourceFacts:{speciesSlaughtered:{swine_slaughter:'1'}}}).text).toContain('The source lists slaughter of pigs.');
  });

  it('requires strict affirmative flags and deduplicates source synonyms', () => {
    const result=classificationExplanation({category:'slaughter',sourceFacts:{speciesSlaughtered:{poultry:true,chicken:'yes',young_chicken_slaughter:'Y',ducks:'No',turkeys:'unknown',pigs:'possible',goats:'0'},processingActivities:{meat_processing:'No',fish_processing:'unknown',dairy_processing:'pending',egg_processing:'false'}}});
    expect(result.text).toContain('The source lists slaughter of chickens.');
    expect(result.text).not.toMatch(/pigs|goats|ducks|turkeys|dairy|egg|processing of/);
  });

  it('uses two supported specific activities including assignment-only and secondary categories', () => {
    const classification={...taxonomy('processing_and_preparation',['fish_processing','dairy_processing','egg_processing']),assignments:[assignment('fish_processing'),assignment('dairy_processing','partial'),assignment('egg_processing','conflicting')]};
    expect(classificationExplanation({taxonomy:classification}).keys).toEqual(['fish_processing','dairy_processing']);
    const mixed={...taxonomy('processing_and_preparation'),primaryCategories:['processing_and_preparation','other_regulated_premises'] as const,assignments:[assignment('meat_processing'),assignment('logistics_and_storage','mapped','other_regulated_premises')]};
    expect(classificationExplanation({taxonomy:mixed}).keys).toEqual(['meat_processing','logistics_and_storage']);
    for(const status of ['conflicting','ambiguous','unmapped','unclassified'] as const) {
      expect(classificationExplanation({taxonomy:{...taxonomy('processing_and_preparation',['dairy_processing']),assignments:[assignment('dairy_processing',status)]}}).keys).toEqual(['processing_and_preparation']);
    }
    expect(classificationExplanation({taxonomy:{...classification,leafActivities:[],assignments:[{...assignment('fish_processing'),method:'candidate'}]}}).keys).toEqual(['processing_and_preparation']);
  });

  it('adds a bounded named species breakdown with an exact remainder and retains its year', () => {
    const annual=namedReport([{species:'Dogs',count:20},{species:'Cats',count:0},{species:'GuineaPigs',count:12},{species:'Non-Human Primates',count:8},{species:'Rabbits',count:7},{species:'Synthetic unknown species',count:3}]);
    const result=classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class R; Class H',aphisAnnualReports:[annual]}});
    expect(result.text).toContain('The fiscal year 2025 report lists 50 animals: dogs: 20, guinea pigs: 12, nonhuman primates: 8, and 10 other reported animals.');
    expect(result.text).not.toMatch(/dead|died|kill|annual estimate|Synthetic/);
    expect(result.references.at(-1)?.href).toBe(annual.sourceUrl);
  });

  it('does not double-count APHIS aliases, pick duplicate years or fall back past a newer invalid report', () => {
    const valid=namedReport([{species:'Dogs',count:100}]);
    const aliases=namedReport([{species:'GuineaPigs',count:12},{species:'guinea-pigs',count:8}]);
    const badMatch={...valid,safeProvenance:{...valid.safeProvenance,matchMethod:'name_similarity'}} as unknown as AphisAnnualReport;
    const negative=namedReport([{species:'Dogs',count:-1}]);
    for(const reports of [[aliases],[valid,valid],[badMatch],[{...valid,fiscalYear:'2024'},negative]]) {
      expect(classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class R',aphisAnnualReports:reports}}).text).not.toContain('report lists');
    }
    expect(classificationExplanation({sourceId:'another.registry',category:'research',sourceFacts:{aphisAnnualReports:[valid]}}).text).not.toContain('report lists');
    expect(classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class T',aphisAnnualReports:[valid]}}).text).not.toContain('report lists');
  });

  it('does not promote an unresolved APHIS assignment or food flag over a registration', () => {
    const unresolved={...assignment('research','ambiguous','research_and_animal_use'),sourceLabel:'Class R - Research Facility'};
    expect(classificationExplanation({sourceId:'us.aphis',taxonomy:{...taxonomy('other_regulated_premises'),assignments:[unresolved]}}).keys).toEqual(['other_regulated_premises']);
    expect(classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class T',speciesSlaughtered:{cattle:true}}}).text).not.toContain('slaughter');
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

  it('localizes named report details, list conjunctions and number formats', () => {
    const annual=namedReport([{species:'Dogs',count:1200},{species:'Cats',count:12}]);
    const messages: Record<string,string>={
      'The fiscal year {year} report lists {count} animals: {breakdown}.':'Rapport {year} : {count} animaux ({breakdown}).',
      '{species}: {count}':'{species} : {count}', dogs:'chiens', cats:'chats',
    };
    const result=classificationExplanation({sourceId:'us.aphis',sourceFacts:{nativeActivityCode:'Class R',aphisAnnualReports:[annual]}},text=>messages[text]??text,'fr');
    expect(result.text).toContain('Rapport 2025 : 1\u202f212 animaux (chiens : 1\u202f200 et chats : 12).');
  });

  it('provides every new generated template and species/product label in all supported translations', () => {
    const keys=[
      'The source lists slaughter of {species}.', 'The source lists slaughter of {species} and processing of {products}.',
      'The source lists processing of {products}.', 'The fiscal year {year} report lists {count} animals: {breakdown}.',
      '{species}: {count}', '{count} other reported animals',
      'cattle','pigs','sheep','goats','horses','bison','chickens','turkeys','ducks','geese','guinea fowl','squabs','ratites','poultry',
      'beef','pork','lamb','goat meat','horse meat','bison meat','poultry meat','chicken meat','turkey meat','duck meat','fish','seafood','dairy products','egg products','meat',
      'dogs','cats','guinea pigs','hamsters','rabbits','nonhuman primates','other farm animals','all other animals',
    ];
    for(const [locale,dictionary] of Object.entries({es,fr,de,nl,da,'zh-Hans':zhHans})) {
      const messages=dictionary as Record<string,string>;
      for(const key of keys) {
        expect(messages[key]?.trim(),`${locale}: ${key}`).toBeTruthy();
        expect(messages[key]?.match(/\{\w+\}/g)?.sort()??[],`${locale}: ${key}`).toEqual(key.match(/\{\w+\}/g)?.sort()??[]);
      }
      for(const key of keys.slice(0,4)) expect(messages[key],`${locale}: ${key}`).not.toBe(key);
    }
  });
  it('builds a Chinese source-backed summary with Chinese product conjunctions', () => {
    const translate = (text: string) => (zhHans as Record<string,string>)[text] ?? text;
    const result = classificationExplanation({category:'processing_and_preparation', sourceFacts:{processingActivities:{raw_non_intact_pork_processing:true,rte_chicken_processing:true}}}, translate, 'zh-Hans');
    expect(result.text).toContain('猪肉');
    expect(result.text).toContain('鸡肉');
    expect(result.text).toContain('来源');
    expect(result.text).not.toMatch(/processing| and |The source|slaughter|killed/);
  });
});
