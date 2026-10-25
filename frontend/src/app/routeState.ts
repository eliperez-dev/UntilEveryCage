export type ContributionType = 'facility' | 'evidence' | 'correction' | 'duplicate' | 'privacy_removal' | 'bug';
export type RouteState =
  | Readonly<{ kind: 'map'; releaseId?: string }>
  | Readonly<{ kind: 'database'; releaseId?: string; returnMapHref?: string }>
  | Readonly<{ kind: 'about'; section: 'overview' | 'sources'; returnMapHref?: string }>
  | Readonly<{ kind: 'downloads'; returnMapHref?: string }>
  | Readonly<{ kind: 'faq'; section?: 'technology' | 'records' | 'contributions' | 'help'; returnMapHref?: string }>
  | Readonly<{ kind: 'api'; returnMapHref?: string }>
  | Readonly<{ kind: 'contribute'; formKind?: ContributionType; targetRecordId?: string; returnMapHref?: string }>
  | Readonly<{ kind: 'bug-report'; returnMapHref?: string }>
  | Readonly<{ kind: 'record'; facilityId: string; profile?: 'official' | 'secondary' | 'community'; releaseId?: string; returnMapHref?: string }>
  | Readonly<{ kind: 'community'; page: 'form' | 'status' | 'claims' | 'claim-detail' | 'review'; formKind?: 'facility' | 'evidence' | 'correction' | 'duplicate' | 'privacy_removal'; claimId?: string; targetRecordId?: string; releaseId?: string; returnMapHref?: string }>
  | Readonly<{ kind: 'not-found'; fragment: string }>;

type RoutableState = Exclude<RouteState, { kind: 'not-found' }>;

const releaseIdPattern = /^[A-Za-z0-9._-]{1,160}$/;

function safeNumeric(params: URLSearchParams, key: string, min: number, max: number): string | undefined {
  const raw = params.get(key);
  if (raw === null || raw.trim() === '') return undefined;
  const value = Number(raw);
  return Number.isFinite(value) && value >= min && value <= max ? String(value) : undefined;
}

export function mapHrefFromParams(params: URLSearchParams, releaseOverride?: string, selectedOverride?: string): string {
  const safe = new URLSearchParams();
  for (const [key, min, max] of [['lat', -90, 90], ['lon', -180, 180], ['z', 1, 18], ['pitch', 0, 85], ['bearing', -180, 180]] as const) {
    const value = safeNumeric(params, key, min, max);
    if (value !== undefined) safe.set(key, value);
  }
  const basemap = params.get('basemap');
  if (basemap === 'satellite' || basemap === 'vector') safe.set('basemap', basemap);
  if (params.get('list') === 'open') safe.set('list', 'open');
  const selected = selectedOverride;
  if (selected && /^[a-z0-9-]{1,80}$/i.test(selected)) safe.set('selected', selected);
  const releaseId = releaseOverride ?? params.get('release_id') ?? undefined;
  if (releaseId && releaseIdPattern.test(releaseId)) safe.set('release_id', releaseId);
  return `#/map${safe.size ? `?${safe}` : ''}`;
}

export function safeMapHref(href: string | undefined | null): string | undefined {
  if (!href || !/^#\/map(?:\?.*)?$/.test(href)) return undefined;
  return mapHrefFromParams(new URLSearchParams(href.split('?')[1] ?? ''));
}

export function mapHrefFromHash(hash: string, releaseOverride?: string): string {
  return mapHrefFromParams(new URLSearchParams(hash.split('?')[1] ?? ''), releaseOverride);
}

export function parseRoute(hash: string): RouteState {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  const [pathPart] = raw.split('?');
  const path = pathPart || '/map';
  const params = new URLSearchParams(raw.split('?')[1] ?? '');
  const requestedMapHref = params.get('map');
  const returnMapHref = safeMapHref(requestedMapHref);

  if (path === '/' || path === '/map') { const releaseId = params.get('release_id'); return { kind: 'map', ...(releaseId && /^[A-Za-z0-9._-]{1,160}$/.test(releaseId) ? { releaseId } : {}) }; }
  if (path === '/database') {
    const releaseId = params.get('release_id');
    const validReleaseId = releaseId && /^[A-Za-z0-9._-]{1,160}$/.test(releaseId) ? releaseId : undefined;
    const requestedContext = safeMapHref(requestedMapHref) ?? mapHrefFromHash(hash, validReleaseId);
    const mapContext = mapHrefFromParams(new URLSearchParams(requestedContext.split('?')[1] ?? ''), validReleaseId);
    return { kind: 'database', ...(validReleaseId ? { releaseId: validReleaseId } : {}), returnMapHref: mapContext };
  }
  if (path === '/methodology' || path === '/about/sources') return { kind: 'faq', section: 'technology', ...(returnMapHref ? { returnMapHref } : {}) };
  if (path === '/about' || path === '/about/manifesto') return { kind: 'about', section: params.get('section') === 'sources' ? 'sources' : 'overview', ...(returnMapHref ? { returnMapHref } : {}) };
  if (path === '/database/downloads') return { kind: 'downloads', ...(returnMapHref ? { returnMapHref } : {}) };
  if (path === '/faq') { const section = params.get('section'); return { kind: 'faq', ...(section && ['technology', 'records', 'contributions', 'help'].includes(section) ? { section: section as 'technology' | 'records' | 'contributions' | 'help' } : {}), ...(returnMapHref ? { returnMapHref } : {}) }; }
  if (path === '/about/faq') return { kind: 'faq', section: 'records', ...(returnMapHref ? { returnMapHref } : {}) };
  if (path === '/database/api' || path === '/about/api') return { kind: 'api', ...(returnMapHref ? { returnMapHref } : {}) };
  if (path === '/about/help') return { kind: 'faq', section: 'help', ...(returnMapHref ? { returnMapHref } : {}) };
  if (path === '/contribute/bug') return { kind: 'bug-report', ...(returnMapHref ? { returnMapHref } : {}) };
  if (path === '/contribute') {
    const targetRecordId = params.get('target');
    const type = params.get('type');
    const formKind = type && ['facility', 'evidence', 'correction', 'duplicate', 'privacy_removal', 'bug'].includes(type) ? type as ContributionType : undefined;
    return { kind: 'contribute', ...(formKind ? { formKind } : {}), ...(targetRecordId ? { targetRecordId } : {}), ...(returnMapHref ? { returnMapHref } : {}) };
  }
  const contributionPath = path.match(/^\/contribute\/(facility|evidence|correction|duplicate|privacy-removal)$/);
  if (contributionPath) {
    const formKind = contributionPath[1] === 'privacy-removal' ? 'privacy_removal' : contributionPath[1] as 'facility' | 'evidence' | 'correction' | 'duplicate';
    const targetRecordId = params.get('target');
    return { kind: 'community', page: 'form', formKind, ...(targetRecordId ? { targetRecordId } : {}), ...(returnMapHref ? { returnMapHref } : {}) };
  }
  if (path === '/contribution-status') return { kind: 'community', page: 'status', ...(returnMapHref ? { returnMapHref } : {}) };
  if (path === '/community') return { kind: 'community', page: 'claims', ...(returnMapHref ? { returnMapHref } : {}) };
  if (path === '/community/claim') {
    const claimId = params.get('id');
    const releaseId = params.get('release_id');
    if (claimId && /^[a-zA-Z0-9-]{1,80}$/.test(claimId) && releaseId && /^[A-Za-z0-9._-]{1,160}$/.test(releaseId)) return { kind: 'community', page: 'claim-detail', claimId, releaseId, ...(returnMapHref ? { returnMapHref } : {}) };
  }
  if (path === '/contribution-review') return { kind: 'community', page: 'review', ...(returnMapHref ? { returnMapHref } : {}) };

  // Keep old shared links working while the public route changes to /records/:id.
  const recordMatch = /^\/(?:records|locations)\/([a-z0-9-]+)$/.exec(path);
  if (recordMatch?.[1]) {
    const profile = params.get('profile'); const releaseId = params.get('release_id');
    const validReleaseId = releaseId && /^[A-Za-z0-9._-]{1,160}$/.test(releaseId) ? releaseId : undefined;
    const mapContext = returnMapHref
      ? mapHrefFromParams(new URLSearchParams(returnMapHref.split('?')[1] ?? ''), validReleaseId)
      : mapHrefFromParams(new URLSearchParams(), validReleaseId);
    return { kind: 'record', facilityId: recordMatch[1], ...(profile && ['official','secondary','community'].includes(profile) ? { profile: profile as 'official' | 'secondary' | 'community' } : {}), ...(validReleaseId ? { releaseId: validReleaseId } : {}), returnMapHref: mapContext };
  }

  return { kind: 'not-found', fragment: raw };
}

export function serializeRoute(route: RoutableState): string {
  if (route.kind === 'map') return `#/map${route.releaseId ? `?release_id=${encodeURIComponent(route.releaseId)}` : ''}`;
  if (route.kind === 'database') { const params = new URLSearchParams({ ...(route.releaseId ? { release_id: route.releaseId } : {}), ...(route.returnMapHref ? { map: route.returnMapHref } : {}) }); return `#/database${params.size ? `?${params}` : ''}`; }
  if (route.kind === 'about') return `#/about${route.section === 'sources' ? '?section=sources' : ''}${route.returnMapHref ? `${route.section === 'sources' ? '&' : '?'}map=${encodeURIComponent(route.returnMapHref)}` : ''}`;
  if (route.kind === 'downloads') return `#/database/downloads${route.returnMapHref ? `?map=${encodeURIComponent(route.returnMapHref)}` : ''}`;
  if (route.kind === 'faq') { const params = new URLSearchParams({ ...(route.section ? { section: route.section } : {}), ...(route.returnMapHref ? { map: route.returnMapHref } : {}) }); return `#/faq${params.size ? `?${params}` : ''}`; }
  if (route.kind === 'api') return `#/database/api${route.returnMapHref ? `?map=${encodeURIComponent(route.returnMapHref)}` : ''}`;
  if (route.kind === 'contribute') return `#/contribute${route.formKind || route.targetRecordId || route.returnMapHref ? `?${new URLSearchParams({ ...(route.formKind ? { type: route.formKind } : {}), ...(route.targetRecordId ? { target: route.targetRecordId } : {}), ...(route.returnMapHref ? { map: route.returnMapHref } : {}) })}` : ''}`;
  if (route.kind === 'bug-report') return `#/contribute/bug${route.returnMapHref ? `?map=${encodeURIComponent(route.returnMapHref)}` : ''}`;
  if (route.kind === 'community') {
    const context = route.returnMapHref ? `map=${encodeURIComponent(route.returnMapHref)}` : '';
    if (route.page === 'form') {
      const path = route.formKind === 'privacy_removal' ? 'privacy-removal' : route.formKind ?? 'facility';
      const params = new URLSearchParams({ ...(route.targetRecordId ? { target: route.targetRecordId } : {}), ...(route.returnMapHref ? { map: route.returnMapHref } : {}) });
      return `#/contribute/${path}${params.size ? `?${params}` : ''}`;
    }
    if (route.page === 'status') return `#/contribution-status${context ? `?${context}` : ''}`;
    if (route.page === 'claims') return `#/community${context ? `?${context}` : ''}`;
    if (route.page === 'claim-detail') return `#/community/claim?id=${encodeURIComponent(route.claimId ?? '')}${route.releaseId ? `&release_id=${encodeURIComponent(route.releaseId)}` : ''}${context ? `&${context}` : ''}`;
    return `#/contribution-review${context ? `?${context}` : ''}`;
  }
  if (route.kind === 'record') { const params = new URLSearchParams({ ...(route.profile ? { profile: route.profile } : {}), ...(route.releaseId ? { release_id: route.releaseId } : {}), ...(route.returnMapHref ? { map: route.returnMapHref } : {}) }); return `#/records/${encodeURIComponent(route.facilityId)}${params.size ? `?${params}` : ''}`; }
  return '#/map';
}
