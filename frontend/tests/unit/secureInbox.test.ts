// @vitest-environment node
import { beforeAll, describe, expect, it, vi } from 'vitest';
import * as openpgp from 'openpgp';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { generateSecureReviewerKey, unlockSecureReviewerKey, prepareSecureSubmission, reviewerSession,
  verifySecureInbox, prepareSecureReply, restoreSecureSession, exportSecureRecovery, secureSessionCredentials,
  rememberSecureSession, getSecureSession, forgetSecureSession, secureTrackingHref, confirmSecureReply,
  type PreparedSecureSubmission } from '../../src/features/contributions/secureInbox';
import { SECURE_CIPHER_BYTES, SECURE_PROTOCOL, type SecureCapabilities, type SecureInbox } from '../../src/api/SecureCommunityRepository';

let reviewer: Awaited<ReturnType<typeof generateSecureReviewerKey>>;
let capabilities: SecureCapabilities;
const now = '2026-10-26T00:00:00Z';
const input = { kind: 'facility', label: 'Synthetic private intake', description: 'Synthetic integration content', consent: true } as const;
function inbox(prepared: PreparedSecureSubmission): SecureInbox {
  const row = prepared.request;
  return { case_id: row.case_id, kind: row.kind, status: 'received', contributor_fingerprint: row.contributor_fingerprint,
    reviewer_fingerprint: row.reviewer_fingerprint, contributor_public_key: row.contributor_public_key,
    reviewer_public_key: reviewer.publicKey, created_at: now, updated_at: now, expires_at: '2027-01-01T00:00:00Z',
    messages: [{ message_id: row.initial_message_id, ordinal: 1, author: 'contributor', ciphertext: row.ciphertext, created_at: now }] };
}
beforeAll(async () => {
  reviewer = await generateSecureReviewerKey();
  capabilities = { enabled: true, mode: 'embedded_sdk', provider: 'openpgpjs-self-hosted', security_status: 'experimental_local_only',
    protocol: SECURE_PROTOCOL, reviewer_public_key: reviewer.publicKey, reviewer_fingerprint: reviewer.fingerprint,
    replies: true, email_alerts: false, max_ciphertext_bytes: SECURE_CIPHER_BYTES };
  // Opt-in, ignored local synthetic fixture. Never runs in CI or ordinary tests.
  if (process.env.UEC_SECURE_BOOTSTRAP === 'true') {
    const dir = resolve('../target/secure-inbox-integration');
    await mkdir(dir, { recursive: true });
    const operator_token = [...crypto.getRandomValues(new Uint8Array(32))].map(byte => byte.toString(16).padStart(2, '0')).join('');
    await writeFile(resolve(dir, 'public-bootstrap.json'), JSON.stringify({ reviewer_public_key: reviewer.publicKey, reviewer_fingerprint: reviewer.fingerprint, operator_token }));
    await writeFile(resolve(dir, 'local-reviewer-recovery.json'), JSON.stringify(reviewer));
  }
});

describe('local encrypted inbox client', () => {
  it('round-trips signed intake and both replies, accepting identical history rereads', async () => {
    const prepared = await prepareSecureSubmission(input, capabilities, reviewer.fingerprint), history = inbox(prepared);
    const key = await unlockSecureReviewerKey(reviewer.encryptedExport, reviewer.recoverySecret, reviewer.fingerprint);
    const review = await reviewerSession(history, key, reviewer.fingerprint);
    expect((await verifySecureInbox(history, review))[0]!.draft).toEqual(input);
    expect((await verifySecureInbox(history, prepared.session))[0]!.draft).toEqual(input);
    const reply = await prepareSecureReply(review, 'Synthetic reviewer question');
    const next = { ...history, messages: [...history.messages, { ...reply, ordinal: 2, author: 'reviewer' as const, created_at: now }] };
    expect((await verifySecureInbox(next, prepared.session))[1]!.text).toBe('Synthetic reviewer question');
    expect(await verifySecureInbox(next, prepared.session)).toHaveLength(2);
    const followup = await prepareSecureReply(prepared.session, 'Synthetic contributor answer');
    expect((await verifySecureInbox({ ...next, messages: [...next.messages, { ...followup, ordinal: 3, author: 'contributor', created_at: now }] }, review))[2]!.text).toBe('Synthetic contributor answer');
    expect(prepared.request.ciphertext).not.toContain(input.label);
    expect(prepared.request.ciphertext).not.toContain('PRIVATE KEY');
  });
  it('rejects changed case/message/author/key metadata and unknown draft fields', async () => {
    const prepared = await prepareSecureSubmission(input, capabilities, reviewer.fingerprint), history = inbox(prepared);
    await expect(verifySecureInbox({ ...history, case_id: crypto.randomUUID() }, prepared.session)).rejects.toThrow();
    await expect(verifySecureInbox({ ...history, messages: [{ ...history.messages[0]!, message_id: crypto.randomUUID() }] }, prepared.session)).rejects.toThrow();
    await expect(verifySecureInbox({ ...history, messages: [{ ...history.messages[0]!, author: 'reviewer' }] }, prepared.session)).rejects.toThrow();
    await expect(verifySecureInbox({ ...history, contributor_fingerprint: reviewer.fingerprint }, prepared.session)).rejects.toThrow();
    await expect(prepareSecureSubmission({ ...input, unexpected: 'must reject' } as typeof input, capabilities, reviewer.fingerprint)).rejects.toThrow();
    await expect(prepareSecureSubmission({ ...input, label: {} } as unknown as typeof input, capabilities, reviewer.fingerprint)).rejects.toThrow();
  });
  it('fails closed for disabled capability and substituted independently pinned reviewer', async () => {
    await expect(prepareSecureSubmission(input, { enabled: false }, reviewer.fingerprint)).rejects.toThrow();
    await expect(prepareSecureSubmission(input, capabilities, '0'.repeat(40))).rejects.toThrow();
    const other = await generateSecureReviewerKey();
    await expect(prepareSecureSubmission(input, { ...capabilities, enabled: true, reviewer_public_key: other.publicKey } as SecureCapabilities, reviewer.fingerprint)).rejects.toThrow();
    await expect(unlockSecureReviewerKey(reviewer.encryptedExport, reviewer.recoverySecret, other.fingerprint)).rejects.toThrow();
  });
  it('rejects unsigned, wrong signer, tampered packets, and oversized decompressed messages', async () => {
    const prepared = await prepareSecureSubmission(input, capabilities, reviewer.fingerprint), history = inbox(prepared);
    const destination = await openpgp.readKey({ armoredKey: prepared.request.contributor_public_key });
    const outsider = await openpgp.generateKey({ type: 'curve25519', userIDs: [{ name: 'Synthetic outsider' }], format: 'object' });
    const seal = async (text: string, sign = false) => openpgp.encrypt({ message: await openpgp.createMessage({ text }), encryptionKeys: destination,
      ...(sign ? { signingKeys: outsider.privateKey } : {}), format: 'armored', config: { preferredCompressionAlgorithm: openpgp.enums.compression.zlib } });
    for (const ciphertext of [await seal('{}'), await seal('{}', true), await seal('X'.repeat(40_000), true), prepared.request.ciphertext.replace(/\n[a-zA-Z0-9]/, '\n!')]) {
      await expect(verifySecureInbox({ ...history, messages: [{ ...history.messages[0]!, ciphertext }] }, prepared.session)).rejects.toThrow();
    }
  });
  it('rejects missing observed history, same-ID conflicts, and reordered messages', async () => {
    const prepared = await prepareSecureSubmission(input, capabilities, reviewer.fingerprint), history = inbox(prepared);
    await verifySecureInbox(history, prepared.session);
    const reply = await prepareSecureReply(prepared.session, 'Synthetic known reply');
    const next = { ...history, messages: [...history.messages, { ...reply, ordinal: 2, author: 'contributor' as const, created_at: now }] };
    await verifySecureInbox(next, prepared.session);
    await expect(verifySecureInbox(history, prepared.session)).rejects.toThrow();
    await expect(verifySecureInbox({ ...next, messages: [{ ...next.messages[1]!, ordinal: 1 }, { ...next.messages[0]!, ordinal: 2 }] }, prepared.session)).rejects.toThrow();
    const replacement = await prepareSecureReply(prepared.session, 'Synthetic altered same ID');
    await expect(verifySecureInbox({ ...next, messages: [next.messages[0]!, { ...next.messages[1]!, ciphertext: replacement.ciphertext }] }, prepared.session)).rejects.toThrow();
  });
  it('recovers keys, API access and history from a local encrypted file plus separate random key', async () => {
    const prepared = await prepareSecureSubmission(input, capabilities, reviewer.fingerprint), history = inbox(prepared);
    await verifySecureInbox(history, prepared.session);
    const recovery = await exportSecureRecovery(prepared.session);
    expect(recovery.recoverySecret).toMatch(/^[0-9a-f]{64}$/);
    expect(recovery.recoverySecret).not.toBe(prepared.request.access_secret);
    expect(recovery.encryptedExport).not.toContain('PRIVATE KEY');
    expect(recovery.encryptedExport).not.toContain(prepared.request.access_secret);
    const restored = await restoreSecureSession(recovery.encryptedExport, recovery.recoverySecret, reviewer.fingerprint);
    expect(secureSessionCredentials(restored)).toEqual({ caseId: prepared.request.case_id, accessSecret: prepared.request.access_secret });
    expect((await verifySecureInbox(history, restored))[0]!.draft).toEqual(input);
    await expect(restoreSecureSession(recovery.encryptedExport, '0'.repeat(64), reviewer.fingerprint)).rejects.toThrow();
    await expect(restoreSecureSession(recovery.encryptedExport, recovery.recoverySecret, '0'.repeat(40))).rejects.toThrow();
    await expect(restoreSecureSession(reviewer.encryptedExport, reviewer.recoverySecret, reviewer.fingerprint)).rejects.toThrow();
  });
  it('pins acknowledged outgoing replies before a first history reread, including a new recovery export', async () => {
    const prepared = await prepareSecureSubmission(input, capabilities, reviewer.fingerprint), history = inbox(prepared);
    await verifySecureInbox(history, prepared.session);
    const reply = await prepareSecureReply(prepared.session, 'Synthetic acknowledged reply');
    confirmSecureReply(prepared.session, reply);
    await expect(verifySecureInbox(history, prepared.session)).rejects.toThrow();
    const saved = await exportSecureRecovery(prepared.session);
    const recovered = await restoreSecureSession(saved.encryptedExport, saved.recoverySecret, reviewer.fingerprint);
    await expect(verifySecureInbox(history, recovered)).rejects.toThrow();
    const next = { ...history, messages: [...history.messages, { ...reply, ordinal: 2, author: 'contributor' as const, created_at: now }] };
    expect(await verifySecureInbox(next, recovered)).toHaveLength(2);
    expect(() => confirmSecureReply(recovered, reply)).toThrow();
  });
  it('uses locale-independent canonical history hashes across recovery', async () => {
    const comparison = vi.spyOn(String.prototype, 'localeCompare').mockImplementation(() => { throw new Error('Locale comparison must not determine cryptographic checkpoints'); });
    try {
      const prepared = await prepareSecureSubmission(input, capabilities, reviewer.fingerprint), history = inbox(prepared);
      const restored = await restoreSecureSession(prepared.recovery.encryptedExport, prepared.recovery.recoverySecret, reviewer.fingerprint);
      expect((await verifySecureInbox(history, restored))[0]!.draft).toEqual(input);
    } finally { comparison.mockRestore(); }
  });
  it('retains only an opaque contributor handle for SPA navigation and explicitly forgets it', async () => {
    const prepared = await prepareSecureSubmission(input, capabilities, reviewer.fingerprint);
    expect(Object.keys(prepared.session).sort()).toEqual(['caseId', 'role']);
    expect(secureTrackingHref(prepared.session)).toMatch(/^#\/secure-inbox\?case_id=/);
    rememberSecureSession(prepared.session); expect(getSecureSession(prepared.session.caseId)).toBe(prepared.session);
    forgetSecureSession(prepared.session.caseId); expect(getSecureSession(prepared.session.caseId)).toBeUndefined();
    expect(() => secureSessionCredentials(prepared.session)).toThrow();
  });
});
