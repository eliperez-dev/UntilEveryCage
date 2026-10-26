import type { ContributionDraft, SubmissionKind } from './CommunityRepository';

export const SECURE_PROTOCOL = 'uec-openpgp-inbox-v1';
export const SECURE_CIPHER_BYTES = 98_304;
export type SecureStatus = 'received' | 'in_review' | 'needs_information' | 'closed' | 'removed';
export type SecureCapabilities = Readonly<{ enabled: false }> | Readonly<{
  enabled: true; mode: 'embedded_sdk'; provider: 'openpgpjs-self-hosted'; security_status: 'experimental_local_only';
  protocol: typeof SECURE_PROTOCOL; reviewer_public_key: string; reviewer_fingerprint: string;
  replies: true; email_alerts: false; max_ciphertext_bytes: number;
}>;
export type SecureCaseSummary = Readonly<{
  case_id: string; kind: SubmissionKind; status: SecureStatus;
  contributor_fingerprint: string; reviewer_fingerprint: string;
  created_at: string; updated_at: string; expires_at: string;
}>;
export type SecureWireMessage = Readonly<{
  message_id: string; ordinal: number; author: 'contributor' | 'reviewer'; ciphertext: string; created_at: string;
}>;
export type SecureInbox = SecureCaseSummary & Readonly<{
  contributor_public_key: string; reviewer_public_key: string; messages: readonly SecureWireMessage[];
}>;
export type PreparedSecureReply = Readonly<{ message_id: string; ciphertext: string }>;
export type SecureSubmissionRequest = Readonly<{
  case_id: string; initial_message_id: string; kind: ContributionDraft['kind']; protocol: typeof SECURE_PROTOCOL;
  access_secret: string; contributor_public_key: string; contributor_fingerprint: string;
  reviewer_fingerprint: string; ciphertext: string;
}>;
export type SecureReceipt = Readonly<{ case_id: string; status: SecureStatus; created_at: string; expires_at: string }>;
export class SecureCommunityError extends Error {
  constructor(message: string, readonly status?: number) { super(message); }
}
export const secureUuid = (value: string): boolean => /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);
export const secureSecret = (value: string): boolean => /^[0-9a-f]{64}$/.test(value);
export const secureFingerprint = (value: string): boolean => /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(value);
const kinds = new Set(['facility', 'evidence', 'correction', 'duplicate', 'privacy_removal', 'bug']);
const statuses = new Set(['received', 'in_review', 'needs_information', 'closed', 'removed']);
const bad = (): never => { throw new SecureCommunityError('The encrypted inbox returned an invalid response.'); };
const bytes = (value: string) => new TextEncoder().encode(value).byteLength;
function record(value: unknown): Record<string, unknown> { if (!value || typeof value !== 'object' || Array.isArray(value)) return bad(); return value as Record<string, unknown>; }
function text(row: Record<string, unknown>, key: string, max: number): string { const value = row[key]; if (typeof value !== 'string' || !value || bytes(value) > max) return bad(); return value; }
function id(row: Record<string, unknown>, key: string): string { const value = text(row, key, 36); if (!secureUuid(value)) return bad(); return value; }
function fp(row: Record<string, unknown>, key: string): string { const value = text(row, key, 64); if (!secureFingerprint(value)) return bad(); return value; }
function date(row: Record<string, unknown>, key: string): string { const value = text(row, key, 64); if (!Number.isFinite(Date.parse(value))) return bad(); return value; }
function publicKey(row: Record<string, unknown>, key: string): string {
  const value = text(row, key, 16_384);
  if (!value.startsWith('-----BEGIN PGP PUBLIC KEY BLOCK-----') || !value.trimEnd().endsWith('-----END PGP PUBLIC KEY BLOCK-----') || value.includes('PRIVATE KEY')) return bad();
  return value;
}
function cipher(row: Record<string, unknown>, key: string): string {
  const value = text(row, key, SECURE_CIPHER_BYTES);
  if (!value.startsWith('-----BEGIN PGP MESSAGE-----') || !value.trimEnd().endsWith('-----END PGP MESSAGE-----') || value.includes('PRIVATE KEY')) return bad();
  return value;
}
function status(row: Record<string, unknown>): SecureStatus { const value = text(row, 'status', 32); if (!statuses.has(value)) return bad(); return value as SecureStatus; }
function summary(value: unknown): SecureCaseSummary {
  const row = record(value), kind = text(row, 'kind', 32); if (!kinds.has(kind)) return bad();
  return { case_id: id(row, 'case_id'), kind: kind as SubmissionKind, status: status(row),
    contributor_fingerprint: fp(row, 'contributor_fingerprint'), reviewer_fingerprint: fp(row, 'reviewer_fingerprint'),
    created_at: date(row, 'created_at'), updated_at: date(row, 'updated_at'), expires_at: date(row, 'expires_at') };
}
function inbox(value: unknown, expectedCase: string): SecureInbox {
  const row = record(value), metadata = summary(row);
  if (metadata.case_id !== expectedCase || !Array.isArray(row.messages) || !row.messages.length || row.messages.length > 32) return bad();
  const seen = new Set<string>();
  const messages = row.messages.map((value, index) => {
    const message = record(value), message_id = id(message, 'message_id');
    if (seen.has(message_id) || message.ordinal !== index + 1 || !['contributor', 'reviewer'].includes(String(message.author))) return bad();
    seen.add(message_id);
    return { message_id, ordinal: index + 1, author: message.author as 'contributor' | 'reviewer',
      ciphertext: cipher(message, 'ciphertext'), created_at: date(message, 'created_at') };
  });
  return { ...metadata, contributor_public_key: publicKey(row, 'contributor_public_key'),
    reviewer_public_key: publicKey(row, 'reviewer_public_key'), messages };
}
type Fetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export function createSecureCommunityRepository(fetcher: Fetch = fetch) {
  async function request<T>(path: string, body: object | undefined, parse: (value: unknown) => T, token?: string): Promise<T> {
    let response: Response;
    try { response = await fetcher(path, { method: body ? 'POST' : 'GET', cache: 'no-store', credentials: 'same-origin',
      headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}) }); }
    catch { throw new SecureCommunityError('The encrypted inbox is unavailable. Try again.'); }
    if (!response.ok) {
      const messages: Record<number, string> = {
        400: 'Some encrypted submission details are invalid.', 401: 'This inbox is unavailable.', 403: 'This inbox is unavailable.',
        404: 'This inbox is unavailable. Check your access or recovery file.',
        409: 'This request conflicts with an existing message. Keep your recovery file.',
        413: 'This encrypted message is too large.', 429: 'The encrypted inbox is at capacity. Try again later.',
      };
      throw new SecureCommunityError(messages[response.status] ?? 'The encrypted inbox is unavailable. Try again.', response.status);
    }
    try { const raw = await response.text(); if (bytes(raw) > 4_000_000) return bad(); return parse(JSON.parse(raw)); }
    catch (error) { if (error instanceof SecureCommunityError) throw error; return bad(); }
  }
  function auth(caseId: string, accessSecret: string) { if (!secureUuid(caseId) || !secureSecret(accessSecret)) throw new SecureCommunityError('Use your private inbox link or recovery file.'); return { case_id: caseId, access_secret: accessSecret }; }
  function operator(token: string): string { if (!token.trim() || token.length > 4096 || /[\r\n]/.test(token)) throw new SecureCommunityError('Enter the reviewer access token.'); return token; }
  function prepared(value: PreparedSecureReply): PreparedSecureReply { const row = record(value); return { message_id: id(row, 'message_id'), ciphertext: cipher(row, 'ciphertext') }; }
  function stored(value: unknown, caseId: string, messageId: string): void { const row = record(value); if (id(row, 'case_id') !== caseId || id(row, 'message_id') !== messageId || row.status !== 'stored') bad(); }
  return {
    capabilities: () => request('/api/community/secure/capabilities', undefined, value => {
      const row = record(value); if (row.enabled === false) return { enabled: false } as const;
      if (row.enabled !== true || row.mode !== 'embedded_sdk' || row.provider !== 'openpgpjs-self-hosted'
        || row.protocol !== SECURE_PROTOCOL || row.security_status !== 'experimental_local_only'
        || row.replies !== true || row.email_alerts !== false || row.max_ciphertext_bytes !== SECURE_CIPHER_BYTES) return bad();
      return { enabled: true, mode: row.mode, provider: row.provider, protocol: SECURE_PROTOCOL,
        security_status: row.security_status, replies: true, email_alerts: false,
        max_ciphertext_bytes: SECURE_CIPHER_BYTES, reviewer_public_key: publicKey(row, 'reviewer_public_key'),
        reviewer_fingerprint: fp(row, 'reviewer_fingerprint') } as SecureCapabilities;
    }),
    submit: (value: SecureSubmissionRequest) => {
      const row = record(value), credentials = auth(id(row, 'case_id'), text(row, 'access_secret', 64));
      if (row.protocol !== SECURE_PROTOCOL || !kinds.has(String(row.kind))) return Promise.reject(new SecureCommunityError('Some encrypted submission details are invalid.'));
      const body: SecureSubmissionRequest = { ...credentials, initial_message_id: id(row, 'initial_message_id'), kind: row.kind as SubmissionKind,
        protocol: SECURE_PROTOCOL, contributor_public_key: publicKey(row, 'contributor_public_key'),
        contributor_fingerprint: fp(row, 'contributor_fingerprint'), reviewer_fingerprint: fp(row, 'reviewer_fingerprint'), ciphertext: cipher(row, 'ciphertext') };
      return request('/api/community/secure/submissions', body, value => {
        const receipt = record(value); if (id(receipt, 'case_id') !== body.case_id) return bad();
        return { case_id: body.case_id, status: status(receipt), created_at: date(receipt, 'created_at'), expires_at: date(receipt, 'expires_at') } as SecureReceipt;
      });
    },
    inbox: (caseId: string, accessSecret: string) => request('/api/community/secure/inbox', auth(caseId, accessSecret), value => inbox(value, caseId)),
    reply: (caseId: string, accessSecret: string, value: PreparedSecureReply) => { const message = prepared(value); return request('/api/community/secure/messages', { ...auth(caseId, accessSecret), ...message }, value => stored(value, caseId, message.message_id)); },
    queue: (token: string) => request('/api/private/community/secure/queue', undefined, value => {
      const row = record(value); if (!Array.isArray(row.cases) || row.cases.length > 20) return bad(); return row.cases.map(summary);
    }, operator(token)),
    reviewerInbox: (token: string, caseId: string) => { if (!secureUuid(caseId)) throw new SecureCommunityError('Choose an inbox.'); return request('/api/private/community/secure/inbox', { case_id: caseId }, value => inbox(value, caseId), operator(token)); },
    reviewerReply: (token: string, caseId: string, reviewerFingerprint: string, value: PreparedSecureReply) => {
      if (!secureUuid(caseId) || !secureFingerprint(reviewerFingerprint)) throw new SecureCommunityError('Choose an inbox and matching reviewer key.');
      const message = prepared(value); return request('/api/private/community/secure/messages', { case_id: caseId, reviewer_fingerprint: reviewerFingerprint, ...message }, value => stored(value, caseId, message.message_id), operator(token));
    },
    disposition: (token: string, caseId: string, nextStatus: SecureStatus) => {
      if (!secureUuid(caseId) || !['in_review', 'needs_information', 'closed', 'removed'].includes(nextStatus)) throw new SecureCommunityError('Choose a supported review status.');
      return request('/api/private/community/secure/disposition', { case_id: caseId, status: nextStatus }, value => { const row = record(value); if (id(row, 'case_id') !== caseId || status(row) !== nextStatus) bad(); }, operator(token));
    },
  };
}
