// @vitest-environment node
/** Opt-in: requires an owned disposable relay, never a production or reference database. */
import { expect, it } from 'vitest';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createSecureCommunityRepository } from '../../src/api/SecureCommunityRepository';
import { prepareSecureSubmission, unlockSecureReviewerKey, reviewerSession, verifySecureInbox,
  prepareSecureReply, restoreSecureSession, secureSessionCredentials, confirmSecureReply } from '../../src/features/contributions/secureInbox';

it.skipIf(process.env.UEC_SECURE_RELAY_INTEGRATION !== 'true')('completes real encrypted intake, reviewer reply, recovery, close and removal on an owned relay', async () => {
  const origin = new URL(process.env.UEC_SECURE_RELAY_ORIGIN ?? '');
  expect(origin.protocol).toBe('http:'); expect(['127.0.0.1', 'localhost']).toContain(origin.hostname);
  const dir = resolve('../target/secure-inbox-integration');
  const bootstrap = JSON.parse(await readFile(resolve(dir, 'public-bootstrap.json'), 'utf8')) as { reviewer_public_key: string; reviewer_fingerprint: string; operator_token: string };
  const localKey = JSON.parse(await readFile(resolve(dir, 'local-reviewer-recovery.json'), 'utf8')) as { encryptedExport: string; recoverySecret: string };
  const sent: string[] = [];
  const repository = createSecureCommunityRepository(async (path, init) => {
    if (init?.body) sent.push(String(init.body));
    return fetch(new URL(String(path), origin), init);
  });
  const capabilities = await repository.capabilities();
  expect(capabilities.enabled).toBe(true);
  const payload = { kind: 'facility', label: 'Synthetic encrypted relay facility', description: 'Synthetic private relay content', consent: true } as const;
  const prepared = await prepareSecureSubmission(payload, capabilities, bootstrap.reviewer_fingerprint);
  await writeFile(resolve(dir, 'sdk-owned-cases.json'), JSON.stringify([prepared.request.case_id]));
  const receipt = await repository.submit(prepared.request);
  expect(receipt.status).toBe('received');
  expect(await repository.submit(prepared.request)).toEqual(receipt);
  await expect(repository.inbox(prepared.request.case_id, '0'.repeat(64))).rejects.toThrow('unavailable');
  const contributorInbox = await repository.inbox(prepared.request.case_id, prepared.request.access_secret);
  expect((await verifySecureInbox(contributorInbox, prepared.session))[0]!.draft).toEqual(payload);
  expect((await repository.queue(bootstrap.operator_token)).some(row => row.case_id === prepared.request.case_id)).toBe(true);
  const key = await unlockSecureReviewerKey(localKey.encryptedExport, localKey.recoverySecret, bootstrap.reviewer_fingerprint);
  const reviewInbox = await repository.reviewerInbox(bootstrap.operator_token, prepared.request.case_id);
  const review = await reviewerSession(reviewInbox, key, bootstrap.reviewer_fingerprint);
  expect((await verifySecureInbox(reviewInbox, review))[0]!.draft).toEqual(payload);
  const question = await prepareSecureReply(review, 'Synthetic reviewer follow-up question');
  await repository.reviewerReply(bootstrap.operator_token, prepared.request.case_id, bootstrap.reviewer_fingerprint, question);
  await repository.reviewerReply(bootstrap.operator_token, prepared.request.case_id, bootstrap.reviewer_fingerprint, question);
  confirmSecureReply(review, question);
  await repository.disposition(bootstrap.operator_token, prepared.request.case_id, 'needs_information');
  const restored = await restoreSecureSession(prepared.recovery.encryptedExport, prepared.recovery.recoverySecret, bootstrap.reviewer_fingerprint);
  const credentials = secureSessionCredentials(restored);
  const updated = await repository.inbox(credentials.caseId, credentials.accessSecret);
  expect(updated.status).toBe('needs_information');
  expect((await verifySecureInbox(updated, restored))[1]!.text).toBe('Synthetic reviewer follow-up question');
  const answer = await prepareSecureReply(restored, 'Synthetic contributor follow-up answer');
  await repository.reply(credentials.caseId, credentials.accessSecret, answer);
  await repository.reply(credentials.caseId, credentials.accessSecret, answer);
  confirmSecureReply(restored, answer);
  expect((await verifySecureInbox(await repository.reviewerInbox(bootstrap.operator_token, credentials.caseId), review))[2]!.text).toBe('Synthetic contributor follow-up answer');
  await repository.disposition(bootstrap.operator_token, credentials.caseId, 'closed');
  expect((await repository.inbox(credentials.caseId, credentials.accessSecret)).status).toBe('closed');
  await expect(repository.reply(credentials.caseId, credentials.accessSecret, await prepareSecureReply(restored, 'Synthetic closed reply'))).rejects.toThrow();
  for (const body of sent) {
    expect(body).not.toContain(payload.label); expect(body).not.toContain(payload.description);
    expect(body).not.toContain('Synthetic reviewer follow-up question'); expect(body).not.toContain('Synthetic contributor follow-up answer');
    expect(body).not.toContain('PRIVATE KEY'); expect(body).not.toContain(localKey.recoverySecret); expect(body).not.toContain(prepared.recovery.recoverySecret);
  }
  await repository.disposition(bootstrap.operator_token, credentials.caseId, 'removed');
  await expect(repository.inbox(credentials.caseId, credentials.accessSecret)).rejects.toThrow('unavailable');
}, 30_000);
