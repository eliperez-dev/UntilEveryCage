/** Synthetic feasibility only. Not imported by the application or a production protocol. */
import * as openpgp from 'openpgp';

export const PROOF_PROTOCOL = 'uec-secure-inbox-synthetic-proof';
export const PROOF_VERSION = 1;
export type Author = 'contributor' | 'reviewer';
export type MessageKind = 'submission' | 'reply';
type Content = Record<string, string | number | boolean | null>;
export type Document = Readonly<{
  protocol: typeof PROOF_PROTOCOL; version: 1; caseId: string; messageId: string;
  author: Author; kind: MessageKind; content: Content;
}>;
export type Expected = Readonly<{ messageId: string; author: Author; kind: MessageKind }>;
export type Identity = Readonly<{ privateKey: openpgp.PrivateKey; publicKey: openpgp.PublicKey }>;
export type TrustedPeer = Readonly<{ armoredPublicKey: string; fingerprint: string }>;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const LIMIT = 32_768;
const CIPHER_LIMIT = 98_304;
const sdkConfig = {
  allowUnauthenticatedMessages: false,
  allowUnauthenticatedStream: false,
  maxDecompressedMessageSize: LIMIT,
};
const invalid = (): never => { throw new Error('Synthetic encrypted message rejected.'); };
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid();
  return value as Record<string, unknown>;
}
function exact(row: Record<string, unknown>, keys: readonly string[]): void {
  if (Object.keys(row).length !== keys.length || keys.some(key => !Object.hasOwn(row, key))) invalid();
}
function bounded(value: string, maximum = LIMIT): void {
  if (new TextEncoder().encode(value).byteLength > maximum) invalid();
}
function parseDocument(text: string): Document {
  bounded(text);
  const row = object(JSON.parse(text));
  exact(row, ['protocol', 'version', 'caseId', 'messageId', 'author', 'kind', 'content']);
  if (row.protocol !== PROOF_PROTOCOL || row.version !== PROOF_VERSION
    || typeof row.caseId !== 'string' || !uuid.test(row.caseId)
    || typeof row.messageId !== 'string' || !uuid.test(row.messageId)
    || !['contributor', 'reviewer'].includes(String(row.author))
    || !['submission', 'reply'].includes(String(row.kind))
    || (row.kind === 'submission' && row.author !== 'contributor')) invalid();
  const content = object(row.content);
  if (!Object.keys(content).length || Object.keys(content).length > 24) invalid();
  for (const [key, value] of Object.entries(content)) {
    if (!/^[a-z_]{1,48}$/.test(key) || ['__proto__', 'constructor', 'prototype'].includes(key)
      || !(value === null || typeof value === 'string' || typeof value === 'boolean'
        || typeof value === 'number' && Number.isFinite(value))) invalid();
  }
  return row as Document;
}
export async function generateIdentity(): Promise<Identity> {
  const pair = await openpgp.generateKey({
    type: 'curve25519', userIDs: [{ name: 'Synthetic inbox endpoint' }], format: 'object',
  });
  return { privateKey: pair.privateKey, publicKey: pair.publicKey };
}
export const trustedPeer = (identity: Identity): TrustedPeer => ({
  armoredPublicKey: identity.publicKey.armor(), fingerprint: identity.publicKey.getFingerprint(),
});
export function makeDocument(caseId: string, author: Author, kind: MessageKind, content: Content): Document {
  return parseDocument(JSON.stringify({ protocol: PROOF_PROTOCOL, version: PROOF_VERSION,
    caseId, messageId: crypto.randomUUID(), author, kind, content }));
}

export class ProofClient {
  private readonly seen = new Set<string>();
  private constructor(readonly caseId: string, readonly role: Author,
    private readonly identity: Identity, private readonly peer: openpgp.PublicKey) {}

  /** Pin must come from an authenticated source. A relay-provided fingerprint is not a trust root. */
  static async create(caseId: string, role: Author, identity: Identity, pin: TrustedPeer): Promise<ProofClient> {
    if (!uuid.test(caseId) || !['contributor', 'reviewer'].includes(role)) invalid();
    const peer = await openpgp.readKey({ armoredKey: pin.armoredPublicKey });
    if (peer.isPrivate() || peer.getFingerprint() !== pin.fingerprint
      || identity.privateKey.getFingerprint() !== identity.publicKey.getFingerprint()
      || !identity.privateKey.isDecrypted() || peer.getFingerprint() === identity.publicKey.getFingerprint()) invalid();
    return new ProofClient(caseId, role, identity, peer);
  }
  async seal(document: Document): Promise<string> {
    const checked = parseDocument(JSON.stringify(document));
    if (checked.caseId !== this.caseId || checked.author !== this.role) invalid();
    return openpgp.encrypt({
      message: await openpgp.createMessage({ text: JSON.stringify(checked) }),
      encryptionKeys: [this.identity.publicKey, this.peer], signingKeys: this.identity.privateKey,
      format: 'armored', config: sdkConfig,
    });
  }
  async open(ciphertext: string, expected: Expected): Promise<Document> {
    try {
      bounded(ciphertext, CIPHER_LIMIT);
      if (!uuid.test(expected.messageId) || !['contributor', 'reviewer'].includes(expected.author)) invalid();
      const result = await openpgp.decrypt({
        message: await openpgp.readMessage({ armoredMessage: ciphertext }),
        decryptionKeys: this.identity.privateKey,
        verificationKeys: expected.author === this.role ? this.identity.publicKey : this.peer,
        expectSigned: true, format: 'utf8', config: sdkConfig,
      });
      // Buffered input only. Do not return/stream decrypted bytes before integrity and signature checks.
      if (typeof result.data !== 'string' || result.signatures.length !== 1) invalid();
      await result.signatures[0]!.verified;
      const document = parseDocument(result.data);
      if (document.caseId !== this.caseId || document.messageId !== expected.messageId
        || document.author !== expected.author || document.kind !== expected.kind
        || this.seen.has(document.messageId)) invalid();
      this.seen.add(document.messageId);
      return document;
    } catch { return invalid(); }
  }
  async exportRecovery(): Promise<{ encryptedExport: string; localRecoverySecret: string }> {
    // Encoding random bytes is not a custom cipher/KDF. The SDK performs password encryption.
    const localRecoverySecret = [...crypto.getRandomValues(new Uint8Array(32))]
      .map(byte => byte.toString(16).padStart(2, '0')).join('');
    const text = JSON.stringify({ protocol: `${PROOF_PROTOCOL}-recovery`, version: PROOF_VERSION,
      caseId: this.caseId, role: this.role, privateKey: this.identity.privateKey.armor(),
      ownFingerprint: this.identity.publicKey.getFingerprint(), peerPublicKey: this.peer.armor(),
      peerFingerprint: this.peer.getFingerprint(), seen: [...this.seen] });
    bounded(text);
    const encryptedExport = await openpgp.encrypt({
      message: await openpgp.createMessage({ text }), passwords: [localRecoverySecret],
      signingKeys: this.identity.privateKey, format: 'armored', config: sdkConfig,
    });
    return { encryptedExport, localRecoverySecret };
  }
  static async recover(encryptedExport: string, localRecoverySecret: string): Promise<ProofClient> {
    try {
      bounded(encryptedExport, CIPHER_LIMIT);
      if (!/^[a-f0-9]{64}$/.test(localRecoverySecret)) invalid();
      // First decrypt is internal and untrusted: extract the self-key, then verify the signed export.
      const decryptOptions = { message: await openpgp.readMessage({ armoredMessage: encryptedExport }),
        passwords: [localRecoverySecret], format: 'utf8' as const, config: sdkConfig };
      const candidate = await openpgp.decrypt(decryptOptions);
      if (typeof candidate.data !== 'string') invalid();
      bounded(candidate.data as string);
      const row = object(JSON.parse(candidate.data as string));
      exact(row, ['protocol', 'version', 'caseId', 'role', 'privateKey', 'ownFingerprint', 'peerPublicKey', 'peerFingerprint', 'seen']);
      if (row.protocol !== `${PROOF_PROTOCOL}-recovery` || row.version !== PROOF_VERSION
        || typeof row.privateKey !== 'string' || typeof row.caseId !== 'string'
        || (row.role !== 'contributor' && row.role !== 'reviewer')
        || typeof row.peerPublicKey !== 'string' || typeof row.peerFingerprint !== 'string'
        || !Array.isArray(row.seen) || row.seen.length > 512
        || row.seen.some(value => typeof value !== 'string' || !uuid.test(value))) invalid();
      const privateKey = await openpgp.readPrivateKey({ armoredKey: row.privateKey as string });
      if (!privateKey.isDecrypted() || privateKey.getFingerprint() !== row.ownFingerprint) invalid();
      const verified = await openpgp.decrypt({ ...decryptOptions,
        message: await openpgp.readMessage({ armoredMessage: encryptedExport }),
        expectSigned: true, verificationKeys: privateKey.toPublic() });
      if (typeof verified.data !== 'string' || verified.data !== candidate.data || verified.signatures.length !== 1) invalid();
      await verified.signatures[0]!.verified;
      const client = await ProofClient.create(row.caseId as string, row.role as Author,
        { privateKey, publicKey: privateKey.toPublic() },
        { armoredPublicKey: row.peerPublicKey as string, fingerprint: row.peerFingerprint as string });
      for (const id of row.seen as string[]) client.seen.add(id);
      return client;
    } catch { return invalid(); }
  }
}

/** The only transport shape in this proof. Auth, storage and API are deliberately mocked. */
export async function sendToMockRelay(document: Document, ciphertext: string,
  post: (body: string) => Promise<void>): Promise<void> {
  bounded(ciphertext, CIPHER_LIMIT);
  await post(JSON.stringify({ case_id: document.caseId, message_id: document.messageId, ciphertext }));
}
