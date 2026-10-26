import { expect, test, type Browser, type BrowserContext, type Page } from '@playwright/test';
import type { Author, MessageKind, TrustedPeer } from '../proofs/secure-inbox-openpgp/cryptoProof';
import type {} from '../proofs/secure-inbox-openpgp/harness';

test.skip(process.env.UEC_SECURE_INBOX_PROOF !== 'true', 'Synthetic SDK proof is explicitly opt-in and requires Vite dev, not the product build.');
const caseId = '18c6ef3a-28cd-4c8e-a9bb-3951f45f210d';
type Wire = { case_id: string; message_id: string; ciphertext: string };

test('independent browser endpoints exchange authenticated ciphertext and recover locally', async ({ browser, baseURL }, testInfo) => {
  test.setTimeout(90_000);
  const posts: string[] = [], unexpected: string[] = [], contexts: BrowserContext[] = [];
  async function endpoint(browser: Browser): Promise<Page> {
    const context = await browser.newContext(); contexts.push(context);
    const page = await context.newPage();
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.origin !== new URL(baseURL!).origin || url.pathname.startsWith('/api/')) {
        unexpected.push(url.origin + url.pathname);
        return route.abort();
      }
      return route.fallback();
    });
    await page.route('**/__synthetic-inbox-proof/relay', route => {
      expect(route.request().method()).toBe('POST');
      posts.push(route.request().postData()!);
      return route.fulfill({ status: 201, contentType: 'application/json', body: '{}' });
    });
    await page.goto('/tests/proofs/secure-inbox-openpgp/index.html');
    await expect.poll(() => page.evaluate(() => Boolean(window.syntheticInboxProof))).toBe(true);
    await page.evaluate(() => {
      const displayLog: string[] = [];
      (window as unknown as { syntheticDisplayLog: string[] }).syntheticDisplayLog = displayLog;
      new MutationObserver(() => displayLog.push(document.querySelector('#result')!.textContent ?? ''))
        .observe(document.querySelector('#result')!, { childList: true, subtree: true, characterData: true });
    });
    return page;
  }
  const initialize = (page: Page, role: Author, pin: TrustedPeer, id = caseId) => page.evaluate(
    ({ id, role, pin }) => window.syntheticInboxProof.initialize(id, role, pin), { id, role, pin });
  const receive = (page: Page, wire: Wire, author: Author, kind: MessageKind) => page.evaluate(
    ({ wire, author, kind }) => window.syntheticInboxProof.receive(wire, author, kind), { wire, author, kind });
  const started = performance.now();
  try {
    const sender = await endpoint(browser), reviewer = await endpoint(browser), stranger = await endpoint(browser);
    const senderPin = await sender.evaluate(() => window.syntheticInboxProof.generate());
    const reviewerPin = await reviewer.evaluate(() => window.syntheticInboxProof.generate());
    const strangerPin = await stranger.evaluate(() => window.syntheticInboxProof.generate());
    await initialize(sender, 'contributor', reviewerPin); await initialize(reviewer, 'reviewer', senderPin);
    await initialize(stranger, 'reviewer', senderPin);
    await sender.evaluate(pin => window.syntheticInboxProof.peerForNegative = pin.armoredPublicKey, reviewerPin);
    await stranger.evaluate(pin => window.syntheticInboxProof.peerForNegative = pin.armoredPublicKey, reviewerPin);

    const initial = await sender.evaluate(() => window.syntheticInboxProof.send('submission', {
      kind: 'facility', label: 'SYNTHETIC_PRIVATE_FACILITY', consent: true,
    }));
    expect(await receive(reviewer, initial, 'contributor', 'submission')).toEqual({ accepted: true });
    expect(await receive(sender, initial, 'contributor', 'submission')).toEqual({ accepted: true });
    expect(await receive(stranger, initial, 'contributor', 'submission')).toEqual({ accepted: false });

    const reply = await reviewer.evaluate(() => window.syntheticInboxProof.send('reply', { text: 'SYNTHETIC_REVIEWER_REPLY' }));
    expect(await receive(sender, reply, 'reviewer', 'reply')).toEqual({ accepted: true });
    const followUp = await sender.evaluate(() => window.syntheticInboxProof.send('reply', { text: 'SYNTHETIC_CONTRIBUTOR_REPLY' }));
    expect(await receive(reviewer, followUp, 'contributor', 'reply')).toEqual({ accepted: true });
    expect(await receive(reviewer, followUp, 'contributor', 'reply')).toEqual({ accepted: false });

    for (const variant of ['unsigned', 'tampered', 'protocol', 'version', 'case', 'message', 'author', 'kind']) {
      const bad = await sender.evaluate(variant => window.syntheticInboxProof.negative(variant), variant);
      expect(await receive(reviewer, bad, 'contributor', 'submission'), variant).toEqual({ accepted: false });
    }
    const forged = await stranger.evaluate(() => window.syntheticInboxProof.negative('forged'));
    expect(await receive(reviewer, forged, 'contributor', 'submission')).toEqual({ accepted: false });
    await expect(sender.evaluate(({ caseId, reviewerPin, strangerPin }) => window.syntheticInboxProof.initialize(caseId, 'contributor',
      { armoredPublicKey: strangerPin.armoredPublicKey, fingerprint: reviewerPin.fingerprint }),
    { caseId, reviewerPin, strangerPin })).rejects.toThrow('Synthetic encrypted message rejected.');

    // Same decryption identity, another case: isolates context binding from wrong-key rejection.
    await initialize(reviewer, 'reviewer', senderPin, '27d7ef4b-39de-4d9f-bacc-4062f560321e');
    expect(await receive(reviewer, initial, 'contributor', 'submission')).toEqual({ accepted: false });
    await initialize(reviewer, 'reviewer', senderPin);
    expect((await reviewer.evaluate(() => (window as unknown as { syntheticDisplayLog: string[] }).syntheticDisplayLog)).join(' '))
      .not.toContain('SYNTHETIC_REJECTED_PLAINTEXT');

    const recovery = await sender.evaluate(() => window.syntheticInboxProof.recovery());
    expect(await sender.evaluate(() => Object.keys(localStorage).length + Object.keys(sessionStorage).length)).toBe(0);
    await sender.context().close(); // A new browser context cannot reuse the original in-memory key.
    const restored = await endpoint(browser);
    expect(await restored.evaluate(({ encryptedExport }) => window.syntheticInboxProof.recover(encryptedExport, 'synthetic-receipt-secret'), recovery)).toBe(false);
    expect(await restored.evaluate(({ encryptedExport }) => window.syntheticInboxProof.recover(encryptedExport, '0'.repeat(64)), recovery)).toBe(false);
    expect(await restored.evaluate(({ encryptedExport, localRecoverySecret }) => window.syntheticInboxProof.recover(encryptedExport, localRecoverySecret), recovery)).toBe(true);
    expect(await receive(restored, reply, 'reviewer', 'reply')).toEqual({ accepted: false });
    const afterRecovery = await reviewer.evaluate(() => window.syntheticInboxProof.send('reply', { text: 'SYNTHETIC_AFTER_RECOVERY' }));
    expect(await receive(restored, afterRecovery, 'reviewer', 'reply')).toEqual({ accepted: true });
    const restoredFollowUp = await restored.evaluate(() => window.syntheticInboxProof.send('reply', { text: 'SYNTHETIC_RESTORED_FOLLOWUP' }));
    expect(await receive(reviewer, restoredFollowUp, 'contributor', 'reply')).toEqual({ accepted: true });

    expect(posts).toHaveLength(5);
    for (const body of posts) {
      expect(Object.keys(JSON.parse(body)).sort()).toEqual(['case_id', 'ciphertext', 'message_id']);
      for (const forbidden of ['SYNTHETIC_', 'PRIVATE KEY', recovery.localRecoverySecret, recovery.encryptedExport, 'receipt-secret']) expect(body).not.toContain(forbidden);
    }
    for (const page of [reviewer, stranger, restored]) {
      expect(await page.evaluate(() => Object.keys(localStorage).length + Object.keys(sessionStorage).length)).toBe(0);
    }
    expect(unexpected).toEqual([]);
    const runtime = await restored.evaluate(() => window.syntheticInboxProof.runtime());
    expect(runtime.secureContext && runtime.subtleCrypto).toBe(true);
    expect(runtime.sdk).toContain('6.3.2');
    const summary = {
      ...runtime, browser: browser.version(), node: process.version,
      fingerprintHexLength: reviewerPin.fingerprint.length, elapsedMs: Math.round(performance.now() - started),
      endpoints: 4, mockRelayPosts: posts.length, negativeCases: 16,
      plaintextOrSecretsTransmitted: false, productionWiring: false,
    };
    console.info('Synthetic encryption proof:', JSON.stringify(summary));
    await testInfo.attach('synthetic-encryption-proof.json', { contentType: 'application/json', body: Buffer.from(JSON.stringify(summary, null, 2)) });
  } finally { await Promise.all(contexts.map(context => context.close())); }
});
