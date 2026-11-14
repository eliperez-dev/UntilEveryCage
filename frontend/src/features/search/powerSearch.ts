import type { LabFilters, LabState, SearchScope } from '../../design-lab/contract';
import type { CandidateFacets } from '../../api/TestReleaseRepository';
import type { LocationFilters } from '../../api/LocalLocationRepository';
import { CATEGORY_PRESENTATIONS } from '../locations/categoryPresentation';
import { isTaxonomyPrimaryKey } from '../../domain/taxonomy';
import { tr, type Language } from '../../app/language';
import { countryOptions as allCountries } from '../../app/countryOptions';
import usStates from '../placeSearch/usStates.json';

// Generalized Natural Earth 1:110m state boundaries, v5.1.2 (public domain).
export const stateSearchName = (code: string) => usStates.find(state => state.code === code)?.name;
export const canSearchRecords = (query: string) => /[\p{L}\p{N}]{3}/u.test(query) || /[\u3400-\u4dbf\u4e00-\u9fff]{2}/u.test(query);

type SearchSelection = { query: string; filters: LabFilters; scope?: SearchScope };
export type SearchSuggestion = Readonly<{ kind: 'country' | 'state' | 'category' | 'source'; value: string; label: string; query: string }>;
type SearchOption = Readonly<{ kind: SearchSuggestion['kind']; value: string; label: string; aliases: readonly string[] }>;
const normalize = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase().trim().replace(/\s+/g, ' ');
const unique = (values: readonly string[]) => [...new Set(values)];

function countryOptions(facets: CandidateFacets | null, locale: Language, includeAllCountries: boolean): SearchOption[] {
  const names = unique([locale, 'en', 'es']).map(language => new Intl.DisplayNames([language], { type: 'region' }));
  const countries = includeAllCountries
    ? allCountries.map(({ code, name }) => ({ value: code, label: name }))
    : (facets?.countries ?? []);
  return countries.filter(country => /^[A-Z]{2}$/.test(country.value)).map(country => {
    const labels = names.map(display => display.of(country.value) ?? country.value);
    return { kind: 'country', value: country.value, label: labels[0] ?? country.label ?? country.value, aliases: unique([country.value, country.label ?? country.value, ...labels]) };
  });
}

function options(facets: CandidateFacets | null, locale: Language, includeStates: boolean): SearchOption[] {
  return [
    ...countryOptions(facets, locale, includeStates),
    ...(includeStates ? usStates.map(({ code, name }): SearchOption => ({ kind: 'state', value: code, label: name, aliases: [name, code] })) : []),
    ...Object.entries(CATEGORY_PRESENTATIONS).map(([value, presentation]): SearchOption => ({ kind: 'category', value, label: tr(presentation.label, locale), aliases: unique([presentation.label, tr(presentation.label, locale), ...(value === 'slaughter' ? ['slaughterhouses', 'slaughterhouse', 'slaughter houses', 'slaughter house', 'mataderos', 'matadero'] : [])]) })),
    ...(facets?.sources ?? []).map(facet => ({ kind: 'source' as const, value: facet.value, label: facet.label ?? facet.value, aliases: unique([facet.value, facet.label ?? facet.value]) })),
  ];
}

const locationSuffix = (query: string) => query.trim().match(/^(.*?)\s+(?:in|en|dans|in der|i)\s+(.+)$/i);
const isPlace = (kind: SearchOption['kind']) => kind === 'country' || kind === 'state';
const exactMatch = (option: SearchOption, term: string) => option.aliases.some(alias => normalize(alias) === term);

export function parseSearch(query: string, filters: LabFilters, facets: CandidateFacets | null, locale: Language = 'en', includeStates = true): SearchSelection {
  const choices = options(facets, locale, includeStates);
  const suffix = locationSuffix(query);
  const placeTerm = normalize(suffix?.[2] ?? query);
  const place = choices.find(option => isPlace(option.kind) && exactMatch(option, placeTerm));
  const remaining = place ? (suffix?.[1] ?? '').trim() : query.trim();
  const category = choices.find(option => option.kind === 'category' && exactMatch(option, normalize(remaining)));
  let result = category ? { ...filters, categories: [category.value] } : filters;
  if (place) result = { ...result, countries: place.kind === 'country' ? [place.value] : [] };
  return {
    query: category ? '' : remaining, filters: result,
    ...(place?.kind === 'state' ? { scope: { kind: 'state', code: place.value } } : {}),
  };
}

export function searchSuggestions(query: string, facets: CandidateFacets | null, locale: Language = 'en', limit = 6, includeStates = true): SearchSuggestion[] {
  const normalized = normalize(query);
  if (normalized.length < 2 && !/\p{Script=Han}/u.test(normalized)) return [];
  const suffix = locationSuffix(query);
  const placeTerm = suffix ? normalize(suffix[2]!) : normalized;
  return options(facets, locale, includeStates).flatMap(option => {
    const term = isPlace(option.kind) ? placeTerm : normalized;
    const aliases = option.aliases.map(normalize);
    const rank = aliases.includes(term) ? 0 : aliases.some(alias => alias.startsWith(term)) ? 1 : aliases.some(alias => alias.includes(term)) ? 2 : -1;
    return rank >= 0 ? [{ option, rank }] : [];
  }).sort((a, b) => a.rank - b.rank).slice(0, Math.min(12, Math.max(0, limit))).map(({ option }) => ({
    kind: option.kind, value: option.value, label: option.label,
    query: isPlace(option.kind) && suffix ? suffix[1]!.trim() : '',
  }));
}

export function applySearchSuggestion(suggestion: SearchSuggestion, filters: LabFilters, facets: CandidateFacets | null = null, locale: Language = 'en'): SearchSelection {
  if (isPlace(suggestion.kind)) {
    const parsed = parseSearch(suggestion.query, filters, facets, locale);
    return {
      ...parsed,
      filters: { ...parsed.filters, countries: suggestion.kind === 'country' ? [suggestion.value] : [] },
      scope: suggestion.kind === 'state' ? { kind: 'state', code: suggestion.value } : null,
    };
  }
  const key = suggestion.kind === 'category' ? 'categories' : 'sources';
  return { query: suggestion.query, filters: { ...filters, [key]: unique([...filters[key], suggestion.value]) } };
}

export function isSearchScope(value: unknown): value is SearchScope {
  if (value === null) return true;
  if (!value || typeof value !== 'object') return false;
  const scope = value as Record<string, unknown>;
  const within = (number: unknown, low: number, high: number) => typeof number === 'number' && Number.isFinite(number) && number >= low && number <= high;
  if (scope.kind === 'radius') return typeof scope.label === 'string' && scope.label.length <= 240 && within(scope.latitude, -90, 90) && within(scope.longitude, -180, 180) && within(scope.radiusKm, .001, 5000);
  if (scope.kind === 'state') return typeof scope.code === 'string' && Boolean(stateSearchName(scope.code));
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
    ...(canSearchRecords(state.query) ? { q: state.query.trim() } : {}),
    category_keys: state.filters.categories.filter(isTaxonomyPrimaryKey),
    ...(state.filters.countries.length ? { country_code: state.filters.countries.join(',') } : {}),
    ...(sourceIds.length ? { source_id: sourceIds.join(',') } : {}),
    ...(state.filters.precisions.length ? { display_precision: state.filters.precisions.join(',') } : {}),
    ...(scope?.kind === 'state' ? { us_state: scope.code } : {}),
    ...(scope?.kind === 'area' ? { min_lon: scope.bounds.west, min_lat: scope.bounds.south, max_lon: scope.bounds.east, max_lat: scope.bounds.north } : {}),
    ...(scope?.kind === 'radius' ? { latitude: scope.latitude, longitude: scope.longitude, radius_km: scope.radiusKm } : {}),
  };
}
