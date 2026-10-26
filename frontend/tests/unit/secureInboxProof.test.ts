// @vitest-environment node
import { beforeAll, describe, expect, it } from 'vitest';
import * as openpgp from 'openpgp';
import { generateIdentity, makeDocument, ProofClient, sendToMockRelay, trustedPeer,
  type Identity, type Document } from '../proofs/secure-inbox-openpgp/cryptoProof';
const caseId = '18c6ef3a-28cd-4c8e-a9bb-3951f45f210d';
const otherCase = '27d7ef4b-39de-4d9f-bacc-4062f560321e';
let contributor: Identity, reviewer: Identity, outsider: Identity;
const expected = (document: Document) => ({ messageId: document.messageId, author: document.author, kind: document.kind });
async function clients(id = caseId) {
  return Promise.all([
    ProofClient.create(id, 'contributor', contributor, trustedPeer(reviewer)),
    ProofClient.create(id, 'reviewer', reviewer, trustedPeer(contributor)),
  ]);
}
async function rawSeal(text: string, signingKeys?: openpgp.PrivateKey) {
  return openpgp.encrypt({ message: await openpgp.createMessage({ text }),
    encryptionKeys: [contributor.publicKey, reviewer.publicKey],
    ...(signingKeys ? { signingKeys } : {}), format: 'armored' });
}
beforeAll(async () => { [contributor, reviewer, outsider] = await Promise.all([generateIdentity(), generateIdentity(), generateIdentity()]); });

describe('synthetic OpenPGP inbox feasibility, never application wiring', () => {
  it('both intended endpoints read a signed structured submission and only ciphertext reaches the mock relay', async () => {
    const [sender, recipient] = await clients();
    const document = makeDocument(caseId, 'contributor', 'submission', { kind: 'facility', label: 'Synthetic private facility', consent: true });
    const ciphertext = await sender!.seal(document);
    const posts: string[] = [];
    await sendToMockRelay(document, ciphertext, async body => { posts.push(body); });
    expect(Object.keys(JSON.parse(posts[0]!)).sort()).toEqual(['case_id', 'ciphertext', 'message_id']);
    expect(posts[0]).not.toContain('Synthetic private facility');
    expect(posts[0]).not.toContain('PRIVATE KEY');
    expect((await recipient!.open(ciphertext, expected(document))).content).toEqual(document.content);
    expect((await sender!.open(ciphertext, expected(document))).content).toEqual(document.content);
  });
  it('authenticates reviewer reply and contributor follow-up against their pinned keys', async () => {
    const [sender, recipient] = await clients();
    const reply = makeDocument(caseId, 'reviewer', 'reply', { text: 'Synthetic reviewer question' });
    const followUp = makeDocument(caseId, 'contributor', 'reply', { text: 'Synthetic contributor response' });
    expect((await sender!.open(await recipient!.seal(reply), expected(reply))).content.text).toBe(reply.content.text);
    expect((await recipient!.open(await sender!.seal(followUp), expected(followUp))).content.text).toBe(followUp.content.text);
  });
  it('rejects unsigned and wrong-signer messages before returning plaintext', async () => {
    const [, recipient] = await clients();
    const document = makeDocument(caseId, 'contributor', 'submission', { label: 'Synthetic not-to-display' });
    await expect(recipient!.open(await rawSeal(JSON.stringify(document)), expected(document))).rejects.toThrow('rejected');
    await expect(recipient!.open(await rawSeal(JSON.stringify(document), outsider.privateKey), expected(document))).rejects.toThrow('rejected');
  });
  it('rejects a wrong decryption key and substituted pinned public key', async () => {
    const [sender] = await clients();
    const stranger = await ProofClient.create(caseId, 'reviewer', outsider, trustedPeer(contributor));
    const document = makeDocument(caseId, 'contributor', 'submission', { label: 'Synthetic confidential' });
    await expect(stranger.open(await sender!.seal(document), expected(document))).rejects.toThrow('rejected');
    await expect(ProofClient.create(caseId, 'contributor', contributor,
      { ...trustedPeer(outsider), fingerprint: reviewer.publicKey.getFingerprint() })).rejects.toThrow('rejected');
  });
  it('rejects byte tampering with encrypted packets', async () => {
    const [, recipient] = await clients();
    const document = makeDocument(caseId, 'contributor', 'submission', { label: 'Synthetic integrity' });
    const bytes = await openpgp.encrypt({ message: await openpgp.createMessage({ text: JSON.stringify(document) }),
      encryptionKeys: reviewer.publicKey, signingKeys: contributor.privateKey, format: 'binary' });
    const tampered = bytes.slice(), index = tampered.length - 12; tampered[index] = tampered[index]! ^ 1;
    const armor = openpgp.armor(openpgp.enums.armor.message, tampered) as string;
    await expect(recipient!.open(armor, expected(document))).rejects.toThrow('rejected');
  });
  it('rejects oversized ciphertext and compressed plaintext before returning any content', async () => {
    const [, recipient] = await clients();
    const document = makeDocument(caseId, 'contributor', 'submission', { label: 'Synthetic bounded message' });
    await expect(recipient!.open('X'.repeat(98_305), expected(document))).rejects.toThrow('rejected');
    const compressed = await openpgp.encrypt({
      message: await openpgp.createMessage({ text: JSON.stringify({ ...document, content: { label: 'X'.repeat(100_000) } }) }),
      encryptionKeys: reviewer.publicKey, signingKeys: contributor.privateKey, format: 'armored',
      config: { preferredCompressionAlgorithm: openpgp.enums.compression.zlib },
    });
    await expect(recipient!.open(compressed, expected(document))).rejects.toThrow('rejected');
  });
  it('binds protocol/version/case/message/author/kind and does not poison replay state on rejection', async () => {
    const [sender, recipient] = await clients();
    const document = makeDocument(caseId, 'contributor', 'submission', { label: 'Synthetic context' });
    for (const patch of [{ protocol: 'other-protocol' }, { version: 2 }, { caseId: otherCase },
      { messageId: crypto.randomUUID() }, { author: 'reviewer' }, { kind: 'reply' }]) {
      await expect(recipient!.open(await rawSeal(JSON.stringify({ ...document, ...patch }), contributor.privateKey), expected(document))).rejects.toThrow('rejected');
    }
    const ciphertext = await sender!.seal(document);
    const other = (await clients(otherCase))[1]!;
    await expect(other.open(ciphertext, expected(document))).rejects.toThrow('rejected');
    await recipient!.open(ciphertext, expected(document));
    await expect(recipient!.open(ciphertext, expected(document))).rejects.toThrow('rejected');
  });
  it('restores a fresh client from a local encrypted export plus independent random secret, preserving known replay IDs', async () => {
    const [sender, recipient] = await clients();
    const first = makeDocument(caseId, 'reviewer', 'reply', { text: 'Synthetic before backup' });
    const firstCipher = await recipient!.seal(first);
    await sender!.open(firstCipher, expected(first));
    const recovery = await sender!.exportRecovery();
    expect(recovery.localRecoverySecret).toMatch(/^[a-f0-9]{64}$/);
    expect(recovery.encryptedExport).not.toContain('PRIVATE KEY');
    expect(recovery.encryptedExport).not.toContain(recovery.localRecoverySecret);
    await expect(ProofClient.recover(recovery.encryptedExport, 'synthetic-receipt-token')).rejects.toThrow('rejected');
    await expect(ProofClient.recover(recovery.encryptedExport, '0'.repeat(64))).rejects.toThrow('rejected');
    const restored = await ProofClient.recover(recovery.encryptedExport, recovery.localRecoverySecret);
    await expect(restored.open(firstCipher, expected(first))).rejects.toThrow('rejected');
    const next = makeDocument(caseId, 'reviewer', 'reply', { text: 'Synthetic after recovery' });
    expect((await restored.open(await recipient!.seal(next), expected(next))).content.text).toBe(next.content.text);
    const followUp = makeDocument(caseId, 'contributor', 'reply', { text: 'Synthetic restored response' });
    expect((await recipient!.open(await restored.seal(followUp), expected(followUp))).content.text).toBe(followUp.content.text);
  });
  it('rejects unsigned and damaged recovery exports before returning a recovered endpoint', async () => {
    const [sender] = await clients();
    const recovery = await sender!.exportRecovery();
    const unsigned = await openpgp.encrypt({ message: await openpgp.createMessage({ text: JSON.stringify({
      protocol: 'uec-secure-inbox-synthetic-proof-recovery', version: 1, caseId, role: 'contributor',
      privateKey: contributor.privateKey.armor(), ownFingerprint: contributor.publicKey.getFingerprint(),
      peerPublicKey: reviewer.publicKey.armor(), peerFingerprint: reviewer.publicKey.getFingerprint(), seen: [],
    }) }), passwords: [recovery.localRecoverySecret], format: 'armored' });
    await expect(ProofClient.recover(unsigned, recovery.localRecoverySecret)).rejects.toThrow('rejected');
    const index = 140, damaged = recovery.encryptedExport.slice(0, index)
      + (recovery.encryptedExport[index] === 'A' ? 'B' : 'A') + recovery.encryptedExport.slice(index + 1);
    await expect(ProofClient.recover(damaged, recovery.localRecoverySecret)).rejects.toThrow('rejected');
  });
});
