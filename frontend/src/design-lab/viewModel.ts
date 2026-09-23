import type { LabRecord, LabState, Precision } from './contract';

export type LabViewModel = Readonly<{
  listRecords: readonly LabRecord[];
  mapRecords: readonly LabRecord[];
  selectedRecord: LabRecord | null;
  unmappedCount: number;
  exactCount: number;
  approximateCount: number;
  isLoading: boolean;
  isEmpty: boolean;
  hasError: boolean;
}>;

export function createLabViewModel(corpus: readonly LabRecord[], state: LabState): LabViewModel {
  const query = state.query.trim().toLocaleLowerCase();
  // The review corpus is intentionally broad; the dense scenario keeps its visual
  // state while retaining every deterministic synthetic point for map inspection.
  const records = corpus;
  const listRecords = state.scenario === 'empty' ? [] : records.filter(record => {
    const searchable = `${record.name} ${record.category} ${record.country} ${record.locality}`.toLocaleLowerCase();
    const matchesQuery = query === '' || searchable.includes(query);
    const matchesCategory = state.filters.categories.length === 0 || state.filters.categories.includes(record.category);
    const matchesPrecision = state.filters.precisions.length === 0 || state.filters.precisions.includes(record.precision);
    return matchesQuery && matchesCategory && matchesPrecision;
  });
  const mapRecords = listRecords.filter(record => record.latitude !== null && record.longitude !== null);
  const selectedRecord = corpus.find(record => record.id === state.selectedId) ?? null;
  const approximate = (precision: Precision) => precision === 'city' || precision === 'coarse';

  return Object.freeze({
    listRecords,
    mapRecords,
    selectedRecord,
    unmappedCount: listRecords.filter(record => record.precision === 'unmapped').length,
    exactCount: mapRecords.filter(record => record.precision === 'exact').length,
    approximateCount: mapRecords.filter(record => approximate(record.precision)).length,
    isLoading: state.scenario === 'loading',
    isEmpty: state.scenario === 'empty' || listRecords.length === 0,
    hasError: state.scenario === 'error',
  });
}
