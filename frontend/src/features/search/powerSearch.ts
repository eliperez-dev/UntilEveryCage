import type { LabFilters, LabState, SearchScope } from '../../design-lab/contract';
import type { CandidateFacets } from '../../api/TestReleaseRepository';
import type { LocationFilters } from '../../api/LocalLocationRepository';
import { CATEGORY_PRESENTATIONS } from '../locations/categoryPresentation';
import { isTaxonomyPrimaryKey } from '../../domain/taxonomy';
import { tr, type Language } from '../../app/language';

export type SearchSuggestion = Readonly<{ kind: 'country' | 'category' | 'source'; value: string; label: string; query: string }>;
type SearchOption = Readonly<{ kind: SearchSuggestion['kind']; value: string; label: string; aliases: readonly string[] }>;
const normalize = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase().trim().replace(/\s+/g, ' ');
const unique = (values: readonly string[]) => [...new Set(values)];

function countryOptions(facets: CandidateFacets | null, locale: Language): SearchOption[] {
  const names = ['en', 'es', locale].map(language => new Intl.DisplayNames([language], { type: 'region' }));
  return (facets?.countries ?? []).filter(facet => /^[A-Z]{2}$/.test(facet.value)).map(facet => {
    const labels = names.map(display => display.of(facet.value) ?? facet.value);
    return { kind: 'country', value: facet.value, label: new Intl.DisplayNames([locale], { type: 'region' }).of(facet.value) ?? facet.label ?? facet.value, aliases: unique([facet.value, facet.label ?? facet.value, ...labels]) };
  });
}

function options(facets: CandidateFacets | null, locale: Language): SearchOption[] {
  return [
    ...countryOptions(facets, locale),
    ...Object.entries(CATEGORY_PRESENTATIONS).map(([value, presentation]): SearchOption => ({ kind: 'category', value, label: tr(presentation.label, locale), aliases: unique([presentation.label, tr(presentation.label, locale), ...(value === 'slaughter' ? ['slaughterhouses', 'slaughterhouse', 'mataderos', 'matadero'] : [])]) })),
    ...(facets?.sources ?? []).map(facet => ({ kind: 'source' as const, value: facet.value, label: facet.label ?? facet.value, aliases: unique([facet.value, facet.label ?? facet.value]) })),
  ];
}

/** Only exact known country suffixes and exact category phrases are interpreted. */
export function parseSearch(query: string, filters: LabFilters, facets: CandidateFacets | null, locale: Language = 'en'): { query: string; filters: LabFilters } {
  let remaining = query.trim();
  let result = filters;
  const suffix = remaining.match(/^(.*?)\s+(?:in|en)\s+(.+)$/i);
  if (suffix) {
    const country = countryOptions(facets, locale).find(option => option.aliases.some(alias => normalize(alias) === normalize(suffix[2]!)));
    if (country) { remaining = suffix[1]!.trim(); result = { ...result, countries: [country.value] }; }
  }
  const category = options(facets, locale).find(option => option.kind === 'category' && option.aliases.some(alias => normalize(alias) === normalize(remaining)));
  if (category) { remaining = ''; result = { ...result, categories: [category.value] }; }
  return { query: remaining, filters: result };
}

export function searchSuggestions(query: string, facets: CandidateFacets | null, locale: Language = 'en', limit = 6): SearchSuggestion[] {
  const normalized = normalize(query);
  if (normalized.length < 2) return [];
  const suffix = query.trim().match(/^(.*?)\s+(?:in|en)\s+(.+)$/i);
  const countryTerm = suffix ? normalize(suffix[2]!) : normalized;
  return options(facets, locale).filter(option => {
    const term = option.kind === 'country' ? countryTerm : normalized;
    return option.aliases.some(alias => normalize(alias).includes(term));
  }).slice(0, Math.min(12, Math.max(0, limit))).map(option => ({
    kind: option.kind, value: option.value, label: option.label,
    query: option.kind === 'country' && suffix ? suffix[1]!.trim() : '',
  }));
}

export function applySearchSuggestion(suggestion: SearchSuggestion, filters: LabFilters): { query: string; filters: LabFilters } {
  const key = suggestion.kind === 'country' ? 'countries' : suggestion.kind === 'category' ? 'categories' : 'sources';
  return { query: suggestion.query, filters: { ...filters, [key]: unique([...filters[key], suggestion.value]) } };
}

export function isSearchScope(value: unknown): value is SearchScope {
  if (value === null) return true;
  if (!value || typeof value !== 'object') return false;
  const scope = value as Record<string, unknown>;
  const within = (number: unknown, low: number, high: number) => typeof number === 'number' && Number.isFinite(number) && number >= low && number <= high;
  if (scope.kind === 'radius') return typeof scope.label === 'string' && scope.label.length <= 240 && within(scope.latitude, -90, 90) && within(scope.longitude, -180, 180) && within(scope.radiusKm, .001, 5000);
  if (scope.kind !== 'area' || !scope.bounds || typeof scope.bounds !== 'object') return false;
  const bounds = scope.bounds as Record<string, unknown>;
  return within(bounds.west, -180, 180) && within(bounds.east, -180, 180) && within(bounds.south, -90, 90) && within(bounds.north, -90, 90) && Number(bounds.south) < Number(bounds.north) && Number(bounds.west) < Number(bounds.east);
}

/** Wrapped views cannot be represented by the API's single bounding box. */
export function areaScopeFromBounds(bounds: import('../../design-lab/contract').ViewportBounds): SearchScope {
  if (![bounds.west, bounds.east, bounds.south, bounds.north].every(Number.isFinite)) return null;
  const span = bounds.east - bounds.west;
  const south = Math.max(-90, bounds.south), north = Math.min(90, bounds.north);
  const shift = Math.floor((bounds.west + 180) / 360) * 360;
  const normalized = span >= 360
    ? { west: -180, east: 180, south, north }
    : { west: bounds.west - shift, east: bounds.east - shift, south, north };
  const scope = { kind: 'area' as const, bounds: normalized };
  return isSearchScope(scope) ? scope : null;
}

/** One projection is shared by the list and the all-matching map request. */
export function publicSearchFilters(state: Pick<LabState, 'query' | 'filters' | 'sourceId' | 'searchScope'>): LocationFilters {
  const scope = state.searchScope;
  if (!isSearchScope(scope)) throw new Error('The selected search area is invalid.');
  const sourceIds = unique([...(state.sourceId ? [state.sourceId] : []), ...state.filters.sources]);
  return {
    ...(state.query.trim() ? { q: state.query.trim() } : {}),
    category_keys: state.filters.categories.filter(isTaxonomyPrimaryKey),
    ...(state.filters.countries.length ? { country_code: state.filters.countries.join(',') } : {}),
    ...(sourceIds.length ? { source_id: sourceIds.join(',') } : {}),
    ...(state.filters.precisions.length ? { display_precision: state.filters.precisions.join(',') } : {}),
    ...(scope?.kind === 'area' ? { min_lon: scope.bounds.west, min_lat: scope.bounds.south, max_lon: scope.bounds.east, max_lat: scope.bounds.north } : {}),
    ...(scope?.kind === 'radius' ? { latitude: scope.latitude, longitude: scope.longitude, radius_km: scope.radiusKm } : {}),
  };
}
