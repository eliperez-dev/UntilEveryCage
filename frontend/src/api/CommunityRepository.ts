export type ContributionKind = 'facility' | 'evidence' | 'correction' | 'duplicate' | 'privacy_removal';
export type ClaimedPrecision = 'unknown' | 'exact' | 'coarse' | 'unmapped';
export type ContributionStatus = 'received' | 'held' | 'screened' | 'rejected' | 'restricted' | 'removed' | 'published';

export type ContributionDraft = Readonly<{
  kind: ContributionKind;
  target_record_id?: string;
  duplicate_record_id?: string;
  label?: string;
  country_code?: string;
  locality?: string;
  claimed_activity?: string;
  location_text?: string;
  claimed_latitude?: number;
  claimed_longitude?: number;
  claimed_precision?: ClaimedPrecision;
  location_input_method?: 'manual_pin' | 'text' | 'unknown';
  source_url?: string;
  observed_on?: string;
  description?: string;
  consent: true;
}>;
export type Receipt = Readonly<{ submission_id: string; receipt_secret: string; status: 'received' }>;
export type StatusResult = Readonly<{ submission_id: string; status: ContributionStatus; public_record_url?: string }>;
export type ReviewRow = Readonly<{
  submission_id: string; kind: ContributionKind; status: ContributionStatus; created_at: string;
  target_record_id?: string; duplicate_record_id?: string; label?: string; country_code?: string;
  locality?: string; claimed_activity?: string; location_text?: string;
  claimed_latitude?: number; claimed_longitude?: number; claimed_precision?: ClaimedPrecision;
  location_input_method?: 'manual_pin' | 'text' | 'unknown';
  source_url?: string; observed_on?: string; description?: string;
}>;
export type ReviewQueue = Readonly<{ submissions: readonly ReviewRow[]; pending_count: number }>;
export type ReviewQueueFilter = 'pending' | ContributionStatus;
export type Disposition = Readonly<{
  action: 'hold' | 'screen' | 'reject' | 'restrict' | 'remove' | 'link_community';
  reason_code: 'privacy' | 'abuse' | 'duplicate' | 'out_of_scope' | 'eligible' | 'other';
  community_record_id?: string;
  release_id?: string;
}>;
export type CommunityClaim = Readonly<{
  submission_id: string; kind: ContributionKind; record_id: string; release_id: string;
  public_record_url: string; origin: 'community-submitted'; factual_review_status: 'unreviewed';
  project_approval: 'not-approved'; warning: string;
}>;
export type CommunityClaims = Readonly<{ claims: readonly CommunityClaim[]; claim_count: number; warning: string }>;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const STATUSES = new Set<ContributionStatus>(['received', 'held', 'screened', 'rejected', 'restricted', 'removed', 'published']);
const KINDS = new Set<ContributionKind>(['facility', 'evidence', 'correction', 'duplicate', 'privacy_removal']);
const PRECISIONS = new Set<ClaimedPrecision>(['unknown', 'exact', 'coarse', 'unmapped']);

export class CommunityError extends Error {
  constructor(readonly category: 'unavailable' | 'invalid' | 'network' | 'unauthorized', message: string) { super(message); }
}
export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new CommunityError('invalid', 'The community service returned an invalid response.');
  return value as Record<string, unknown>;
}
function string(row: Record<string, unknown>, field: string, max: number, optional = false): string | undefined {
  const value = row[field];
  if ((value === undefined || value === null) && optional) return undefined;
  if (typeof value !== 'string' || (!optional && value.length === 0) || value.length > max) throw new CommunityError('invalid', 'The community service returned an invalid response.');
  return value;
}
function safeHttpUrl(value: unknown, max: number): string {
  if (typeof value !== 'string' || value.length > max) throw new CommunityError('invalid', 'The community service returned an invalid response.');
  try { const url = new URL(value); if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error(); return value; }
  catch { throw new CommunityError('invalid', 'The community service returned an invalid response.'); }
}
function safeCommunityPublicUrl(value: unknown, max: number, expectedRelease?: string): string {
  if (typeof value !== 'string' || value.length > max || value.startsWith('//')) throw new CommunityError('invalid', 'The community service returned an invalid public link.');
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin || url.username || url.password || url.hash
      || !(/^\/api\/community\/claims\/[0-9a-f-]{36}$/i.test(url.pathname) || /^\/api\/v2\/locations\/[0-9a-f-]{36}$/i.test(url.pathname))
      || url.searchParams.get('profile') !== 'community'
      || !url.searchParams.get('release_id')
      || (expectedRelease !== undefined && url.searchParams.get('release_id') !== expectedRelease)) throw new Error('unsafe community URL');
    return `${url.pathname}${url.search}`;
  } catch { throw new CommunityError('invalid', 'The community service returned an invalid public link.'); }
}
function coordinate(value: unknown, minimum: number, maximum: number): number | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== 'number' || !Number.isFinite(value) || value < minimum || value > maximum) throw new CommunityError('invalid', 'The community service returned an invalid response.');
  return value;
}
function status(value: unknown): ContributionStatus {
  if (typeof value !== 'string' || !STATUSES.has(value as ContributionStatus)) throw new CommunityError('invalid', 'The community service returned an invalid response.');
  return value as ContributionStatus;
}
function kind(value: unknown): ContributionKind {
  if (typeof value !== 'string' || !KINDS.has(value as ContributionKind)) throw new CommunityError('invalid', 'The community service returned an invalid response.');
  return value as ContributionKind;
}
function parseReceipt(value: unknown): Receipt {
  const row = record(value);
  const submission_id = string(row, 'submission_id', 36)!;
  const receipt_secret = string(row, 'receipt_secret', 80)!;
  if (!UUID.test(submission_id) || row.status !== 'received') throw new CommunityError('invalid', 'The community service returned an invalid response.');
  return { submission_id, receipt_secret, status: 'received' };
}
function parseReviewRow(value: unknown): ReviewRow {
  const row = record(value);
  const submission_id = string(row, 'submission_id', 36)!;
  const created_at = string(row, 'created_at', 40)!;
  const lat = coordinate(row.claimed_latitude, -90, 90);
  const lon = coordinate(row.claimed_longitude, -180, 180);
  if (!UUID.test(submission_id) || !Number.isFinite(Date.parse(created_at)) || ((lat === undefined) !== (lon === undefined))) throw new CommunityError('invalid', 'The community service returned an invalid response.');
  const precision = row.claimed_precision;
  if (precision !== undefined && precision !== null && (typeof precision !== 'string' || !PRECISIONS.has(precision as ClaimedPrecision))) throw new CommunityError('invalid', 'The community service returned an invalid response.');
  const inputMethod = row.location_input_method;
  if (inputMethod !== undefined && inputMethod !== null && (typeof inputMethod !== 'string' || !['manual_pin','text','unknown'].includes(inputMethod))) throw new CommunityError('invalid', 'The community service returned an invalid response.');
  const targetRecordId = string(row, 'target_record_id', 36, true);
  const duplicateRecordId = string(row, 'duplicate_record_id', 36, true);
  const label = string(row, 'label', 160, true);
  const countryCode = string(row, 'country_code', 2, true);
  const locality = string(row, 'locality', 160, true);
  const activity = string(row, 'claimed_activity', 160, true);
  const locationText = string(row, 'location_text', 1000, true);
  const sourceUrl = string(row, 'source_url', 2048, true);
  const observedOn = string(row, 'observed_on', 10, true);
  const description = string(row, 'description', 2000, true);
  if (targetRecordId && !UUID.test(targetRecordId) || duplicateRecordId && !UUID.test(duplicateRecordId)) throw new CommunityError('invalid', 'The community service returned an invalid response.');
  return {
    submission_id, kind: kind(row.kind), status: status(row.status), created_at,
    ...(targetRecordId !== undefined ? { target_record_id: targetRecordId } : {}),
    ...(duplicateRecordId !== undefined ? { duplicate_record_id: duplicateRecordId } : {}),
    ...(label !== undefined ? { label } : {}),
    ...(countryCode !== undefined ? { country_code: countryCode } : {}),
    ...(locality !== undefined ? { locality } : {}),
    ...(activity !== undefined ? { claimed_activity: activity } : {}),
    ...(locationText !== undefined ? { location_text: locationText } : {}),
    ...(lat !== undefined ? { claimed_latitude: lat, claimed_longitude: lon! } : {}),
    ...(precision !== undefined && precision !== null ? { claimed_precision: precision as ClaimedPrecision } : {}),
    ...(inputMethod !== undefined && inputMethod !== null ? { location_input_method: inputMethod as 'manual_pin' | 'text' | 'unknown' } : {}),
    ...(sourceUrl !== undefined ? { source_url: safeHttpUrl(sourceUrl, 2048) } : {}),
    ...(observedOn !== undefined ? { observed_on: observedOn } : {}),
    ...(description !== undefined ? { description } : {}),
  };
}
async function request<T>(fetcher: FetchLike, path: string, init: RequestInit, parse: (body: unknown) => T): Promise<T> {
  let response: Response;
  try { response = await fetcher(path, { ...init, cache: 'no-store', headers: { 'Content-Type': 'application/json', ...init.headers }, credentials: 'same-origin' }); }
  catch { throw new CommunityError('network', 'The community service is unavailable. Your information was not shown again.'); }
  if (!response.ok) throw new CommunityError(response.status === 401 || response.status === 403 ? 'unauthorized' : 'unavailable', response.status === 401 || response.status === 403 ? 'The operator credential was not accepted.' : 'The community service is unavailable.');
  try { return parse(await response.json()); } catch (error) { if (error instanceof CommunityError) throw error; throw new CommunityError('invalid', 'The community service returned an invalid response.'); }
}
export function validateContributionDraft(draft: ContributionDraft): void {
  if (!draft.consent || !KINDS.has(draft.kind)) throw new CommunityError('invalid', 'Consent is required.');
  if (draft.target_record_id && !UUID.test(draft.target_record_id)) throw new CommunityError('invalid', 'Enter a valid record identifier.');
  if (draft.duplicate_record_id && !UUID.test(draft.duplicate_record_id)) throw new CommunityError('invalid', 'Enter a valid duplicate record identifier.');
  if (draft.kind === 'facility' && (!draft.label || !draft.country_code || !draft.source_url)) throw new CommunityError('invalid', 'Facility claims need a label, country, and source.');
  if (draft.kind === 'evidence' && (!draft.target_record_id || !draft.source_url)) throw new CommunityError('invalid', 'Evidence needs a target record and source.');
  if (draft.kind === 'correction' && (!draft.target_record_id || !draft.description)) throw new CommunityError('invalid', 'Corrections need a target record and explanation.');
  if (draft.kind === 'duplicate' && (!draft.target_record_id || !draft.duplicate_record_id || draft.target_record_id === draft.duplicate_record_id)) throw new CommunityError('invalid', 'Choose two different record identifiers.');
  if (draft.kind === 'privacy_removal' && (!draft.target_record_id || !draft.description)) throw new CommunityError('invalid', 'Privacy requests need a target record and explanation.');
  if ((draft.claimed_latitude === undefined) !== (draft.claimed_longitude === undefined)) throw new CommunityError('invalid', 'Choose a complete latitude and longitude pair.');
  if (draft.claimed_latitude !== undefined) coordinate(draft.claimed_latitude, -90, 90);
  if (draft.claimed_longitude !== undefined) coordinate(draft.claimed_longitude, -180, 180);
  if (draft.location_input_method !== undefined && !['manual_pin','text','unknown'].includes(draft.location_input_method)) throw new CommunityError('invalid', 'Choose a supported location input method.');
  if (draft.location_input_method === 'manual_pin' && draft.claimed_latitude === undefined) throw new CommunityError('invalid', 'Place a pin before selecting map input as the location method.');
  if (draft.source_url) safeHttpUrl(draft.source_url, 2048);
  for (const [field, max] of [['label',160],['locality',160],['claimed_activity',160],['location_text',1000],['description',2000]] as const) {
    const value = draft[field]; if (value !== undefined && value.length > max) throw new CommunityError('invalid', `${field} is too long.`);
  }
  if (draft.country_code && !/^[A-Za-z]{2}$/.test(draft.country_code)) throw new CommunityError('invalid', 'Use a two-letter country code.');
  if (draft.observed_on && (!/^\d{4}-\d{2}-\d{2}$/.test(draft.observed_on) || Number.isNaN(Date.parse(`${draft.observed_on}T00:00:00Z`)))) throw new CommunityError('invalid', 'Enter a valid observation date.');
}

export function createCommunityRepository(fetcher: FetchLike = fetch) {
  return {
    submit(draft: ContributionDraft) {
      validateContributionDraft(draft);
      return request(fetcher, '/api/community/submissions', { method: 'POST', body: JSON.stringify(draft) }, parseReceipt);
    },
    status(submissionId: string, receiptSecret: string) {
      if (!UUID.test(submissionId) || !receiptSecret.trim() || receiptSecret.length > 80) throw new CommunityError('invalid', 'Enter the receipt details you saved.');
      return request(fetcher, '/api/community/status', { method: 'POST', body: JSON.stringify({ submission_id: submissionId, receipt_secret: receiptSecret }) }, body => {
        const row = record(body); const id = string(row, 'submission_id', 36)!;
        if (!UUID.test(id)) throw new CommunityError('invalid', 'The community service returned an invalid response.');
        return { submission_id: id, status: status(row.status), ...(row.public_record_url === undefined ? {} : { public_record_url: safeCommunityPublicUrl(row.public_record_url, 2048) }) } satisfies StatusResult;
      });
    },
    async queue(token: string, limit = 50, filter: ReviewQueueFilter = 'pending') {
      if (!token || token.length > 4096) throw new CommunityError('unauthorized', 'Enter the local operator credential.');
      const boundedLimit = Math.min(50, Math.max(1, Math.floor(limit)));
      const requestStatus = async (selected?: ContributionStatus) => request(fetcher, `/api/private/community/submissions?limit=${boundedLimit}${selected ? `&status=${selected}` : ''}`, { method: 'GET', headers: { Authorization: `Bearer ${token}` } }, body => {
        const row = record(body);
        if (!Array.isArray(row.submissions) || typeof row.pending_count !== 'number' || !Number.isInteger(row.pending_count) || row.pending_count < 0) throw new CommunityError('invalid', 'The community service returned an invalid queue.');
        return { submissions: row.submissions.map(parseReviewRow), pending_count: row.pending_count } satisfies ReviewQueue;
      });
      if (filter === 'pending') return requestStatus();
      if (!STATUSES.has(filter)) throw new CommunityError('invalid', 'Choose a supported queue status.');
      return requestStatus(filter);
    },
    currentCommunityReleaseId() {
      return request(fetcher, '/api/v2/releases/manifest?profile=community', { method: 'GET', headers: { Accept: 'application/json' } }, body => {
        const envelope = record(body);
        const data = record(envelope.data);
        const releaseId = string(data, 'release_id', 160)!;
        if (envelope.api_version !== 'v2' || data.profile !== 'community' || !/^[A-Za-z0-9._-]{1,160}$/.test(releaseId)) throw new CommunityError('invalid', 'The current community release is unavailable.');
        return releaseId;
      });
    },
    disposition(token: string, id: string, decision: Disposition) {
      if (!token || !UUID.test(id) || !['hold','screen','reject','restrict','remove','link_community'].includes(decision.action)
        || !['privacy','abuse','duplicate','out_of_scope','eligible','other'].includes(decision.reason_code)
        || (decision.action === 'link_community' && (!decision.community_record_id || !UUID.test(decision.community_record_id) || !decision.release_id?.trim()))) {
        throw new CommunityError('invalid', 'Select a valid queue item and disposition.');
      }
      return request(fetcher, `/api/private/community/submissions/${encodeURIComponent(id)}/disposition`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify(decision) }, body => record(body));
    },
    claims(releaseId: string) {
      const params = new URLSearchParams({ profile: 'community', release_id: releaseId });
      return request(fetcher, `/api/community/claims?${params}`, { method: 'GET' }, body => {
        const row = record(body);
        if (!Array.isArray(row.claims) || row.claims.length > 500 || typeof row.claim_count !== 'number' || !Number.isInteger(row.claim_count) || row.claim_count !== row.claims.length || row.claim_count < 0 || typeof row.warning !== 'string') throw new CommunityError('invalid', 'The community service returned an invalid profile.');
        const claims = row.claims.map((item): CommunityClaim => {
          const claim = record(item);
          if (claim.origin !== 'community-submitted' || claim.factual_review_status !== 'unreviewed' || claim.project_approval !== 'not-approved') throw new CommunityError('invalid', 'The community service returned an invalid claim.');
          const claimRelease = string(claim, 'release_id', 160)!;
          const url = safeCommunityPublicUrl(claim.public_record_url, 2048, claimRelease);
          return { submission_id: string(claim, 'submission_id', 36)!, kind: kind(claim.kind), record_id: string(claim, 'record_id', 36)!, release_id: string(claim, 'release_id', 160)!, public_record_url: url, origin: 'community-submitted', factual_review_status: 'unreviewed', project_approval: 'not-approved', warning: string(claim, 'warning', 1000)! };
        });
        return { claims, claim_count: row.claim_count, warning: string(row, 'warning', 1000)! } satisfies CommunityClaims;
      });
    },
    claim(id: string, releaseId: string) {
      const params = new URLSearchParams({ profile: 'community', release_id: releaseId });
      return request(fetcher, `/api/community/claims/${encodeURIComponent(id)}?${params}`, { method: 'GET' }, body => {
        const row = record(body);
        if (row.origin !== 'community-submitted' || row.factual_review_status !== 'unreviewed' || row.project_approval !== 'not-approved') throw new CommunityError('invalid', 'The community service returned an invalid claim.');
        const release = string(row, 'release_id', 160)!;
        return { submission_id: string(row, 'submission_id', 36)!, kind: kind(row.kind), record_id: string(row, 'record_id', 36)!, release_id: release, public_record_url: safeCommunityPublicUrl(row.public_record_url, 2048, release), origin: 'community-submitted', factual_review_status: 'unreviewed', project_approval: 'not-approved', warning: string(row, 'warning', 1000)! } satisfies CommunityClaim;
      });
    },
  };
}
