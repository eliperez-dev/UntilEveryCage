/** Local-only encrypted inbox. Never import this module from an ungated public route. */
import * as openpgp from 'openpgp';
import { validateContributionDraft, type ContributionDraft, type SubmissionKind } from '../../api/CommunityRepository';
import { SECURE_PROTOCOL, SECURE_CIPHER_BYTES, secureFingerprint, secureSecret, secureUuid,
  type SecureCapabilities, type SecureInbox, type SecureSubmissionRequest, type PreparedSecureReply } from '../../api/SecureCommunityRepository';
export type { PreparedSecureReply } from '../../api/SecureCommunityRepository';

type Author = 'contributor' | 'reviewer';
export type SecureSession = Readonly<{ caseId: string; role: Author }>;
export type ReviewerKey = Readonly<{ publicKey: string; fingerprint: string }>;
export type VerifiedSecureMessage = Readonly<{
  id: string; author: Author; createdAt: string; kind: 'submission' | 'reply'; draft?: ContributionDraft; text?: string;
}>;
export type PreparedSecureSubmission = Readonly<{
  request: SecureSubmissionRequest; session: SecureSession;
  recovery: Readonly<{ encryptedExport: string; recoverySecret: string }>;
}>;
type State = {
  privateKey: openpgp.PrivateKey; contributor: openpgp.PublicKey; reviewer: openpgp.PublicKey;
  kind: SubmissionKind; accessSecret?: string; checkpoint: Map<string, string>; acknowledged: Map<string, string>; verified: boolean;
};
type Envelope = {
  protocol: typeof SECURE_PROTOCOL; version: 1; case_id: string; message_id: string; author: Author;
  message_type: 'submission' | 'reply'; contributor_fingerprint: string; reviewer_fingerprint: string;
  payload: { draft: ContributionDraft } | { text: string };
};
const states = new WeakMap<SecureSession, State>();
const reviewerKeys = new WeakMap<ReviewerKey, openpgp.PrivateKey>();
const preparedReplies = new WeakMap<PreparedSecureReply, { session: SecureSession; hash: string; ciphertext: string }>();
const remembered = new Map<string, SecureSession>();
const kinds = new Set(['facility', 'evidence', 'correction', 'duplicate', 'privacy_removal', 'bug']);
const config = { allowUnauthenticatedMessages: false, allowUnauthenticatedStream: false, maxDecompressedMessageSize: 32_768 };
const encoder = new TextEncoder();
const fail = (): never => { throw new Error('This encrypted inbox could not be verified. Check your key and access details.'); };
function bounded(value: string, max = 32_768): void { if (encoder.encode(value).byteLength > max) fail(); }
function object(value: unknown): Record<string, unknown> { if (!value || typeof value !== 'object' || Array.isArray(value)) fail(); return value as Record<string, unknown>; }
function exact(row: Record<string, unknown>, keys: readonly string[]): void {
  if (Object.keys(row).length !== keys.length || Object.keys(row).some(key => !keys.includes(key))) fail();
}
function string(value: unknown, max: number): string { if (typeof value !== 'string') fail(); bounded(value as string, max); return value as string; }
function field(value: unknown, max: number): string { if (typeof value !== 'string' || value.length > max) fail(); return value as string; }
function fingerprint(value: unknown): string { const result = string(value, 64); if (!secureFingerprint(result)) fail(); return result; }
function uuid(value: unknown): string { const result = string(value, 36); if (!secureUuid(result)) fail(); return result; }
function secret(): string { return [...crypto.getRandomValues(new Uint8Array(32))].map(byte => byte.toString(16).padStart(2, '0')).join(''); }
function state(session: SecureSession): State { const value = states.get(session); if (!value) fail(); return value!; }
function createSession(caseId: string, role: Author, value: State): SecureSession {
  const session = Object.freeze({ caseId: uuid(caseId), role }); states.set(session, value); return session;
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(',')}}`;
  return JSON.stringify(value);
}
async function digest(document: Envelope, ordinal: number): Promise<string> {
  return hash(`${ordinal}:${canonical(document)}`);
}
async function hash(text: string): Promise<string> {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(text)))].map(byte => byte.toString(16).padStart(2, '0')).join('');
}
async function publicKey(armor: string, expected: string): Promise<openpgp.PublicKey> {
  bounded(armor, 16_384); fingerprint(expected);
  if (!armor.startsWith('-----BEGIN PGP PUBLIC KEY BLOCK-----') || armor.includes('PRIVATE KEY')) fail();
  const key = await openpgp.readKey({ armoredKey: armor });
  if (key.isPrivate() || key.getFingerprint() !== expected) fail();
  await key.verifyPrimaryKey(); await key.getEncryptionKey(); await key.getSigningKey();
  return key.toPublic();
}
async function identity(name: string): Promise<openpgp.PrivateKey> {
  const generated = await openpgp.generateKey({ type: 'curve25519', userIDs: [{ name }], format: 'object' });
  return generated.privateKey;
}
function draft(value: unknown): ContributionDraft {
  const row = object(value);
  const limits: Record<string, number> = { kind: 32, target_record_id: 36, duplicate_record_id: 36, label: 160,
    country_code: 2, locality: 160, claimed_activity: 160, location_text: 1000, claimed_precision: 16,
    location_input_method: 16, source_url: 2048, observed_on: 10, description: 2000, expected_behavior: 1000,
    reproduction_steps: 2000, page_url: 1000, contact_email: 254 };
  for (const [key, value] of Object.entries(row)) {
    if (key === 'consent') { if (value !== true) fail(); }
    else if (key === 'claimed_latitude' || key === 'claimed_longitude') { if (typeof value !== 'number' || !Number.isFinite(value)) fail(); }
    else if (limits[key] === undefined) fail();
    else field(value, limits[key]!);
  }
  if (!kinds.has(String(row.kind)) || row.consent !== true) fail();
  if (row.claimed_precision !== undefined && !['unknown', 'exact', 'coarse', 'unmapped'].includes(String(row.claimed_precision))) fail();
  validateContributionDraft(row as ContributionDraft);
  return JSON.parse(JSON.stringify(row)) as ContributionDraft;
}
function envelope(value: unknown): Envelope {
  const row = object(value);
  exact(row, ['protocol', 'version', 'case_id', 'message_id', 'author', 'message_type', 'contributor_fingerprint', 'reviewer_fingerprint', 'payload']);
  if (row.protocol !== SECURE_PROTOCOL || row.version !== 1 || !['contributor', 'reviewer'].includes(String(row.author))
    || !['submission', 'reply'].includes(String(row.message_type))) fail();
  uuid(row.case_id); uuid(row.message_id); fingerprint(row.contributor_fingerprint); fingerprint(row.reviewer_fingerprint);
  const payload = object(row.payload);
  if (row.message_type === 'submission') { exact(payload, ['draft']); payload.draft = draft(payload.draft); if (row.author !== 'contributor') fail(); }
  else { exact(payload, ['text']); if (!field(payload.text, 8000).trim()) fail(); }
  return row as unknown as Envelope;
}
async function encrypt(document: Envelope, value: State): Promise<string> {
  const text = JSON.stringify(document); bounded(text);
  const ciphertext = await openpgp.encrypt({ message: await openpgp.createMessage({ text }),
    encryptionKeys: [value.contributor, value.reviewer], signingKeys: value.privateKey, format: 'armored', config });
  bounded(ciphertext, SECURE_CIPHER_BYTES); return ciphertext;
}
function document(session: SecureSession, messageId: string, payload: Envelope['payload']): Envelope {
  const value = state(session);
  return { protocol: SECURE_PROTOCOL, version: 1, case_id: session.caseId, message_id: messageId, author: session.role,
    message_type: 'draft' in payload ? 'submission' : 'reply', contributor_fingerprint: value.contributor.getFingerprint(),
    reviewer_fingerprint: value.reviewer.getFingerprint(), payload };
}
export async function prepareSecureSubmission(input: ContributionDraft, capabilities: SecureCapabilities, expectedFingerprint: string): Promise<PreparedSecureSubmission> {
  try {
    if (!capabilities.enabled) return fail();
    if (capabilities.protocol !== SECURE_PROTOCOL || capabilities.reviewer_fingerprint !== expectedFingerprint) fail();
    const reviewer = await publicKey(capabilities.reviewer_public_key, fingerprint(expectedFingerprint));
    const content = draft(input), privateKey = await identity('Until Every Cage contributor');
    const session = createSession(crypto.randomUUID(), 'contributor', { privateKey, contributor: privateKey.toPublic(), reviewer,
      kind: content.kind, accessSecret: secret(), checkpoint: new Map(), acknowledged: new Map(), verified: false });
    const value = state(session), initial = document(session, crypto.randomUUID(), { draft: content });
    const ciphertext = await encrypt(initial, value);
    value.checkpoint.set(initial.message_id, await digest(initial, 1));
    return { request: { case_id: session.caseId, initial_message_id: initial.message_id, kind: content.kind, protocol: SECURE_PROTOCOL,
      access_secret: value.accessSecret!, contributor_public_key: value.contributor.armor(), contributor_fingerprint: value.contributor.getFingerprint(),
      reviewer_fingerprint: reviewer.getFingerprint(), ciphertext }, session, recovery: await exportSecureRecovery(session) };
  } catch { return fail(); }
}
export function rememberSecureSession(session: SecureSession): void {
  state(session); if (session.role !== 'contributor') fail(); remembered.delete(session.caseId); remembered.set(session.caseId, session);
  if (remembered.size > 8) remembered.delete(remembered.keys().next().value!);
}
export function getSecureSession(caseId: string): SecureSession | undefined { return remembered.get(caseId); }
export function forgetSecureSession(caseId: string): void { const session = remembered.get(caseId); if (session) states.delete(session); remembered.delete(caseId); }
export function secureSessionCredentials(session: SecureSession): { caseId: string; accessSecret: string } {
  const value = state(session); if (session.role !== 'contributor' || !value.accessSecret) fail(); return { caseId: session.caseId, accessSecret: value.accessSecret! };
}
export function secureTrackingHref(session: SecureSession): string { const value = secureSessionCredentials(session); return `#/secure-inbox?case_id=${value.caseId}&access_secret=${value.accessSecret}`; }
export async function verifySecureInbox(inbox: SecureInbox, session: SecureSession): Promise<VerifiedSecureMessage[]> {
  try {
    const value = state(session);
    if (inbox.case_id !== session.caseId || inbox.kind !== value.kind || inbox.contributor_fingerprint !== value.contributor.getFingerprint()
      || inbox.reviewer_fingerprint !== value.reviewer.getFingerprint() || inbox.messages.length < 1 || inbox.messages.length > 32) fail();
    await publicKey(inbox.contributor_public_key, value.contributor.getFingerprint());
    await publicKey(inbox.reviewer_public_key, value.reviewer.getFingerprint());
    const checked = new Map<string, string>(), contentHashes = new Map<string, string>(), result: VerifiedSecureMessage[] = [];
    for (const [index, wire] of inbox.messages.entries()) {
      bounded(wire.ciphertext, SECURE_CIPHER_BYTES);
      if (wire.ordinal !== index + 1 || checked.has(wire.message_id) || !['contributor', 'reviewer'].includes(wire.author)) fail();
      const opened = await openpgp.decrypt({ message: await openpgp.readMessage({ armoredMessage: wire.ciphertext }),
        decryptionKeys: value.privateKey, verificationKeys: wire.author === 'contributor' ? value.contributor : value.reviewer,
        expectSigned: true, format: 'utf8', config });
      if (typeof opened.data !== 'string' || opened.signatures.length !== 1) fail();
      await opened.signatures[0]!.verified;
      const text = opened.data as string; bounded(text);
      const item = envelope(JSON.parse(text));
      if (item.case_id !== session.caseId || item.message_id !== wire.message_id || item.author !== wire.author
        || item.contributor_fingerprint !== value.contributor.getFingerprint() || item.reviewer_fingerprint !== value.reviewer.getFingerprint()
        || item.message_type !== (index === 0 ? 'submission' : 'reply')) fail();
      if ('draft' in item.payload && item.payload.draft.kind !== value.kind) fail();
      checked.set(item.message_id, await digest(item, wire.ordinal));
      contentHashes.set(item.message_id, await hash(canonical(item)));
      result.push({ id: item.message_id, author: item.author, createdAt: wire.created_at, kind: item.message_type,
        ...('draft' in item.payload ? { draft: item.payload.draft } : { text: item.payload.text }) });
    }
    for (const [id, hash] of value.checkpoint) if (checked.get(id) !== hash) fail();
    for (const [id, hash] of value.acknowledged) if (contentHashes.get(id) !== hash) fail();
    value.checkpoint = checked; value.acknowledged.clear(); value.verified = true; return result;
  } catch { return fail(); }
}
export async function prepareSecureReply(session: SecureSession, text: string): Promise<PreparedSecureReply> {
  try {
    const value = state(session); if (!value.verified || !field(text, 8000).trim()) fail();
    const message_id = crypto.randomUUID(), item = document(session, message_id, { text });
    const reply = Object.freeze({ message_id, ciphertext: await encrypt(item, value) });
    preparedReplies.set(reply, { session, hash: await hash(canonical(item)), ciphertext: reply.ciphertext });
    return reply;
  } catch { return fail(); }
}
/** Call only after the API acknowledges this exact prepared object. */
export function confirmSecureReply(session: SecureSession, reply: PreparedSecureReply): void {
  const prepared = preparedReplies.get(reply), value = state(session);
  if (!prepared || prepared.session !== session || prepared.ciphertext !== reply.ciphertext) fail();
  value.acknowledged.set(reply.message_id, prepared!.hash);
}
async function recoveryExport(payload: object, key: openpgp.PrivateKey): Promise<{ encryptedExport: string; recoverySecret: string }> {
  const text = JSON.stringify(payload); bounded(text); const recoverySecret = secret();
  const encryptedExport = await openpgp.encrypt({ message: await openpgp.createMessage({ text }), passwords: [recoverySecret], signingKeys: key, format: 'armored', config });
  bounded(encryptedExport, SECURE_CIPHER_BYTES); return { encryptedExport, recoverySecret };
}
export async function exportSecureRecovery(session: SecureSession): Promise<{ encryptedExport: string; recoverySecret: string }> {
  const value = state(session); if (session.role !== 'contributor' || !value.accessSecret) fail();
  return recoveryExport({ protocol: `${SECURE_PROTOCOL}-recovery`, version: 1, role: 'contributor', case_id: session.caseId,
    kind: value.kind, access_secret: value.accessSecret, private_key: value.privateKey.armor(), contributor_fingerprint: value.contributor.getFingerprint(),
    reviewer_public_key: value.reviewer.armor(), reviewer_fingerprint: value.reviewer.getFingerprint(), checkpoint: [...value.checkpoint], acknowledged: [...value.acknowledged] }, value.privateKey);
}
async function openRecovery(encryptedExport: string, recoverySecret: string): Promise<{ row: Record<string, unknown>; key: openpgp.PrivateKey }> {
  bounded(encryptedExport, SECURE_CIPHER_BYTES); if (!secureSecret(recoverySecret)) fail();
  const options = { passwords: [recoverySecret], format: 'utf8' as const, config };
  const candidate = await openpgp.decrypt({ ...options, message: await openpgp.readMessage({ armoredMessage: encryptedExport }) });
  if (typeof candidate.data !== 'string') fail(); const text = candidate.data as string; bounded(text);
  const row = object(JSON.parse(text));
  if (row.protocol !== `${SECURE_PROTOCOL}-recovery` || row.version !== 1) fail();
  const key = await openpgp.readPrivateKey({ armoredKey: string(row.private_key, 16_384) });
  if (!key.isDecrypted()) fail(); await key.verifyPrimaryKey(); await key.getEncryptionKey(); await key.getSigningKey();
  const verified = await openpgp.decrypt({ ...options, message: await openpgp.readMessage({ armoredMessage: encryptedExport }),
    verificationKeys: key.toPublic(), expectSigned: true });
  if (typeof verified.data !== 'string' || verified.data !== text || verified.signatures.length !== 1) fail();
  await verified.signatures[0]!.verified; return { row, key };
}
export async function restoreSecureSession(encryptedExport: string, recoverySecret: string, expectedFingerprint: string): Promise<SecureSession> {
  try {
    const { row, key } = await openRecovery(encryptedExport, recoverySecret);
    exact(row, ['protocol', 'version', 'role', 'case_id', 'kind', 'access_secret', 'private_key', 'contributor_fingerprint', 'reviewer_public_key', 'reviewer_fingerprint', 'checkpoint', 'acknowledged']);
    if (row.role !== 'contributor' || !kinds.has(String(row.kind)) || !secureSecret(String(row.access_secret))
      || key.getFingerprint() !== fingerprint(row.contributor_fingerprint) || row.reviewer_fingerprint !== fingerprint(expectedFingerprint)
      || !Array.isArray(row.checkpoint) || row.checkpoint.length > 32 || !Array.isArray(row.acknowledged) || row.acknowledged.length > 32) fail();
    function checkpoints(entries: unknown): Map<string, string> {
      const values = new Map<string, string>();
      for (const entry of entries as unknown[]) {
        if (!Array.isArray(entry) || entry.length !== 2 || !secureSecret(String(entry[1]))) fail();
        const pair = entry as unknown[], id = uuid(pair[0]); if (values.has(id)) fail(); values.set(id, String(pair[1]));
      }
      return values;
    }
    const checkpoint = checkpoints(row.checkpoint), acknowledged = checkpoints(row.acknowledged);
    const reviewer = await publicKey(string(row.reviewer_public_key, 16_384), expectedFingerprint);
    return createSession(uuid(row.case_id), 'contributor', { privateKey: key, contributor: key.toPublic(), reviewer,
      kind: row.kind as SubmissionKind, accessSecret: row.access_secret as string, checkpoint, acknowledged, verified: false });
  } catch { return fail(); }
}
export async function generateSecureReviewerKey(): Promise<{ publicKey: string; fingerprint: string; encryptedExport: string; recoverySecret: string }> {
  const key = await identity('Until Every Cage reviewer');
  return { publicKey: key.toPublic().armor(), fingerprint: key.getFingerprint(),
    ...await recoveryExport({ protocol: `${SECURE_PROTOCOL}-recovery`, version: 1, role: 'reviewer', private_key: key.armor(), reviewer_fingerprint: key.getFingerprint() }, key) };
}
export async function unlockSecureReviewerKey(encryptedExport: string, recoverySecret: string, expectedFingerprint: string): Promise<ReviewerKey> {
  try {
    const { row, key } = await openRecovery(encryptedExport, recoverySecret);
    exact(row, ['protocol', 'version', 'role', 'private_key', 'reviewer_fingerprint']);
    if (row.role !== 'reviewer' || row.reviewer_fingerprint !== fingerprint(expectedFingerprint) || key.getFingerprint() !== expectedFingerprint) fail();
    const handle = Object.freeze({ publicKey: key.toPublic().armor(), fingerprint: key.getFingerprint() }); reviewerKeys.set(handle, key); return handle;
  } catch { return fail(); }
}
export async function reviewerSession(inbox: SecureInbox, reviewerKey: ReviewerKey, expectedFingerprint: string): Promise<SecureSession> {
  try {
    const key = reviewerKeys.get(reviewerKey);
    if (!key || key.getFingerprint() !== fingerprint(expectedFingerprint) || inbox.reviewer_fingerprint !== expectedFingerprint) fail();
    const contributor = await publicKey(inbox.contributor_public_key, inbox.contributor_fingerprint);
    const reviewer = await publicKey(inbox.reviewer_public_key, expectedFingerprint);
    return createSession(inbox.case_id, 'reviewer', { privateKey: key!, contributor, reviewer, kind: inbox.kind, checkpoint: new Map(), acknowledged: new Map(), verified: false });
  } catch { return fail(); }
}
