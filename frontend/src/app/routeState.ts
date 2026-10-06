export type ContributionType = 'facility' | 'evidence' | 'correction' | 'duplicate' | 'privacy_removal' | 'bug';
export type RouteState =
  | Readonly<{ kind: 'map' }>
  | Readonly<{ kind: 'database' }>
  | Readonly<{ kind: 'methodology'; returnMapHref?: string }>
  | Readonly<{ kind: 'about'; section: 'overview'; returnMapHref?: string }>
  | Readonly<{ kind: 'help'; returnMapHref?: string }>
  | Readonly<{ kind: 'api'; returnMapHref?: string }>
  | Readonly<{ kind: 'contribute'; formKind?: ContributionType; targetRecordId?: string; returnMapHref?: string }>
  | Readonly<{ kind: 'bug-report'; returnMapHref?: string }>
  | Readonly<{ kind: 'record'; facilityId: string }>
  | Readonly<{ kind: 'community'; page: 'form' | 'status' | 'claims' | 'claim-detail' | 'review'; formKind?: 'facility' | 'evidence' | 'correction' | 'duplicate' | 'privacy_removal'; claimId?: string; targetRecordId?: string; releaseId?: string; returnMapHref?: string }>
  | Readonly<{ kind: 'not-found'; fragment: string }>;

type RoutableState = Exclude<RouteState, { kind: 'not-found' }>;

export function parseRoute(hash: string): RouteState {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash;
  const [pathPart] = raw.split('?');
  const path = pathPart || '/map';
  const params = new URLSearchParams(raw.split('?')[1] ?? '');
  const requestedMapHref = params.get('map');
  const returnMapHref = requestedMapHref && /^#\/map(?:\?.*)?$/.test(requestedMapHref) ? requestedMapHref : undefined;

  if (path === '/' || path === '/map') return { kind: 'map' };
  if (path === '/database') return { kind: 'database' };
  if (path === '/methodology' || path === '/about/sources') return { kind: 'methodology', ...(returnMapHref ? { returnMapHref } : {}) };
  if (path === '/about' || path === '/about/manifesto') return { kind: 'about', section: 'overview', ...(returnMapHref ? { returnMapHref } : {}) };
  if (path === '/about/help' || path === '/about/api') return { kind: path === '/about/help' ? 'help' : 'api', ...(returnMapHref ? { returnMapHref } : {}) };
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
  if (recordMatch?.[1]) return { kind: 'record', facilityId: recordMatch[1] };

  return { kind: 'not-found', fragment: raw };
}

export function serializeRoute(route: RoutableState): string {
  if (route.kind === 'map') return '#/map';
  if (route.kind === 'database') return '#/database';
  if (route.kind === 'methodology') return `#/methodology${route.returnMapHref ? `?map=${encodeURIComponent(route.returnMapHref)}` : ''}`;
  if (route.kind === 'about') return `#/about${route.returnMapHref ? `?map=${encodeURIComponent(route.returnMapHref)}` : ''}`;
  if (route.kind === 'help' || route.kind === 'api') return `#/about/${route.kind}${route.returnMapHref ? `?map=${encodeURIComponent(route.returnMapHref)}` : ''}`;
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
  return `#/records/${encodeURIComponent(route.facilityId)}`;
}
