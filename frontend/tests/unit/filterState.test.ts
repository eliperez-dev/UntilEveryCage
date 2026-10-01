import { describe, expect, it } from 'vitest';
import { locations } from '../../src/fixtures/locations';
import type { Location } from '../../src/domain/location';
import { filterLocations, initialFilters } from '../../src/features/locations/filterState';

const classified: readonly Location[] = [
  {
    ...locations[0]!, id: 'multi-activity', source: 'Feed A', sourceId: 'feed-a', category: 'legacy-source-label',
    taxonomy: {
      displayCategory: 'slaughter', primaryCategories: ['slaughter', 'processing_and_preparation'],
      leafActivities: [{ key: 'slaughter', label: 'Animal slaughter' }, { key: 'cutting', label: 'Meat cutting' }],
      assignments: [], taxonomyVersion: 'uec-taxonomy-v1',
    },
  },
  {
    ...locations[1]!, id: 'research-record', source: 'Feed B', sourceId: 'feed-b', category: 'laboratory',
    taxonomy: {
      displayCategory: 'research_and_animal_use', primaryCategories: ['research_and_animal_use'],
      leafActivities: [{ key: 'animal-testing', label: 'Animal use in research' }],
      assignments: [], taxonomyVersion: 'uec-taxonomy-v1',
    },
  },
];

describe('filterLocations', () => {
  it('searches names, regions, legacy categories, leaf activities, and source labels', () => {
    expect(filterLocations(locations, { ...initialFilters, search: 'dairy' })).toHaveLength(1);
    expect(filterLocations(locations, { ...initialFilters, search: 'north coast' })).toHaveLength(1);
    expect(filterLocations(classified, { ...initialFilters, search: 'animal use in research' }).map(row => row.id)).toEqual(['research-record']);
    expect(filterLocations(classified, { ...initialFilters, search: 'cutting' }).map(row => row.id)).toEqual(['multi-activity']);
    expect(filterLocations(classified, { ...initialFilters, search: 'slaughter' }).map(row => row.id)).toEqual(['multi-activity']);
  });

  it('composes independent filters with OR within category and AND across source', () => {
    const result = filterLocations(classified, {
      ...initialFilters,
      categories: ['processing_and_preparation', 'research_and_animal_use'],
      source: 'feed-a',
    });
    expect(result.map(row => row.id)).toEqual(['multi-activity']);
    expect(filterLocations(classified, { ...initialFilters, categories: ['slaughter'], source: 'feed-b' })).toEqual([]);
  });

  it('treats records without recognized taxonomy as unclassified', () => {
    const unknown = { ...locations[0]!, id: 'unknown', category: 'future-source-category' };
    expect(filterLocations([unknown], { ...initialFilters, categories: ['unclassified'] })).toEqual([unknown]);
  });

  it('retains the compatibility scalar category filter and returns no match explicitly', () => {
    expect(filterLocations(classified, { ...initialFilters, category: 'legacy-source-label' }).map(row => row.id)).toEqual(['multi-activity']);
    expect(filterLocations(locations, { ...initialFilters, search: 'unknown place' })).toEqual([]);
  });
});
