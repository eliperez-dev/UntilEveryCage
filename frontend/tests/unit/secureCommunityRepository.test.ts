import { describe, expect, it } from 'vitest';
import { createSecureCommunityRepository, SECURE_CIPHER_BYTES, SECURE_PROTOCOL, type SecureSubmissionRequest } from '../../src/api/SecureCommunityRepository';
const caseId = '18c6ef3a-28cd-4c8e-a9bb-3951f45f210d', messageId = '27d7ef4b-39de-4d9f-bacc-4062f560321e';
const fp = '1'.repeat(40), accessSecret = '2'.repeat(64), now = '2026-10-26T00:00:00Z';
const armor = '-----BEGIN PGP PUBLIC KEY BLOCK-----\nsynthetic framing only\n-----END PGP PUBLIC KEY BLOCK-----';
const cipher = '-----BEGIN PGP MESSAGE-----\nsynthetic framing only\n-----END PGP MESSAGE-----';
const metadata = { case_id: caseId, kind: 'facility', status: 'received', contributor_fingerprint: fp, reviewer_fingerprint: fp, created_at: now, updated_at: now, expires_at: now };
const history = { ...metadata, contributor_public_key: armor, reviewer_public_key: armor, messages: [{ message_id: messageId, ordinal: 1, author: 'contributor', ciphertext: cipher, created_at: now }] };
const submission: SecureSubmissionRequest = { case_id: caseId, initial_message_id: messageId, kind: 'facility', protocol: SECURE_PROTOCOL,
  access_secret: accessSecret, contributor_public_key: armor, contributor_fingerprint: fp, reviewer_fingerprint: fp, ciphertext: cipher };
describe('encrypted relay transport boundary (framing, not cryptographic verification)', () => {
  it('sends credentials in POST bodies only and strips accidental plaintext fields', async () => {
    const requests: { path: string; init: RequestInit }[] = [];
    const repository = createSecureCommunityRepository(async (path, init) => { requests.push({ path: String(path), init: init! }); return Response.json(String(path).endsWith('/inbox') ? history : { case_id: caseId, status: 'received', created_at: now, expires_at: now }); });
    await repository.submit({ ...submission, label: 'must not travel', privateKey: 'must not travel' } as SecureSubmissionRequest);
    await repository.inbox(caseId, accessSecret);
    expect(JSON.parse(String(requests[0]!.init.body))).toEqual(submission);
    expect(JSON.parse(String(requests[1]!.init.body))).toEqual({ case_id: caseId, access_secret: accessSecret });
    for (const request of requests) {
      expect(request.path).not.toContain(accessSecret); expect(request.path).not.toContain('?');
      expect(request.init.cache).toBe('no-store'); expect(request.init.method).toBe('POST');
      expect(String(request.init.body)).not.toContain('must not travel');
    }
  });
  it('unwraps bounded reviewer metadata and uses bearer auth only in its header', async () => {
    let observed: RequestInit | undefined;
    const repository = createSecureCommunityRepository(async (path, init) => { expect(String(path)).toBe('/api/private/community/secure/queue'); observed = init; return Response.json({ cases: [metadata] }); });
    expect(await repository.queue('synthetic-token')).toEqual([metadata]);
    expect(observed?.body).toBeUndefined(); expect(observed?.headers).toHaveProperty('Authorization', 'Bearer synthetic-token');
  });
  it('accepts only the implemented local capability and independently configured protocol/limits', async () => {
    const capability = { enabled: true, mode: 'embedded_sdk', provider: 'openpgpjs-self-hosted', security_status: 'experimental_local_only', protocol: SECURE_PROTOCOL,
      reviewer_public_key: armor, reviewer_fingerprint: fp, replies: true, email_alerts: false, max_ciphertext_bytes: SECURE_CIPHER_BYTES };
    expect(await createSecureCommunityRepository(async () => Response.json(capability)).capabilities()).toEqual(capability);
    expect(await createSecureCommunityRepository(async () => Response.json({ enabled: false })).capabilities()).toEqual({ enabled: false });
    for (const change of [{ email_alerts: true }, { max_ciphertext_bytes: 999999 }, { security_status: 'production' }, { protocol: 'other' }, { reviewer_public_key: '-----BEGIN PGP PRIVATE KEY BLOCK-----' }]) {
      await expect(createSecureCommunityRepository(async () => Response.json({ ...capability, ...change })).capabilities()).rejects.toThrow('invalid response');
    }
  });
  it('rejects malformed, duplicate, out-of-order or cross-case history', async () => {
    for (const bad of [{ ...history, case_id: messageId }, { ...history, messages: [] }, { ...history, messages: [...history.messages, history.messages[0]] },
      { ...history, messages: [{ ...history.messages[0], ordinal: 2 }] }, { ...history, messages: [{ ...history.messages[0], author: 'unknown' }] },
      { ...history, messages: [{ ...history.messages[0], ciphertext: 'plaintext' }] }, { ...history, contributor_fingerprint: 'short' }]) {
      await expect(createSecureCommunityRepository(async () => Response.json(bad)).inbox(caseId, accessSecret)).rejects.toThrow('invalid response');
    }
  });
  it('returns safe errors without reflecting server bodies or throwing network details', async () => {
    for (const status of [400, 401, 404, 409, 413, 429, 503]) {
      const repository = createSecureCommunityRepository(async () => new Response('synthetic sensitive server detail', { status }));
      await expect(repository.inbox(caseId, accessSecret)).rejects.not.toThrow('sensitive');
    }
    await expect(createSecureCommunityRepository(async () => { throw new Error('synthetic sensitive URL'); }).inbox(caseId, accessSecret)).rejects.not.toThrow('sensitive');
  });
  it('rejects unsupported operations and credentials before touching the network', async () => {
    let calls = 0; const repository = createSecureCommunityRepository(async () => { calls++; return Response.json({}); });
    expect(() => repository.inbox(caseId, 'bad')).toThrow();
    expect(() => repository.queue('bad\r\ntoken')).toThrow();
    expect(() => repository.disposition('token', caseId, 'published' as 'closed')).toThrow();
    expect(calls).toBe(0);
  });
  it('retains the exact prepared reply for retry and validates matching acknowledgement', async () => {
    const bodies: string[] = [], prepared = { message_id: messageId, ciphertext: cipher };
    const repository = createSecureCommunityRepository(async (_path, init) => { bodies.push(String(init?.body)); return Response.json({ case_id: caseId, message_id: messageId, status: 'stored' }); });
    await repository.reply(caseId, accessSecret, prepared); await repository.reply(caseId, accessSecret, prepared);
    expect(bodies[0]).toBe(bodies[1]);
    await expect(createSecureCommunityRepository(async () => Response.json({ case_id: caseId, message_id: crypto.randomUUID(), status: 'stored' })).reply(caseId, accessSecret, prepared)).rejects.toThrow('invalid response');
  });
});
