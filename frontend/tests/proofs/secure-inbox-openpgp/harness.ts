/** Test-only browser adapter. No application route imports this harness. */
import * as openpgp from 'openpgp';
import { generateIdentity, makeDocument, ProofClient, sendToMockRelay, trustedPeer,
  type Author, type Document, type Identity, type MessageKind, type TrustedPeer } from './cryptoProof';
let identity: Identity | undefined, client: ProofClient | undefined;
let currentCase = '', currentRole: Author = 'contributor';
type Wire = { case_id: string; message_id: string; ciphertext: string };
const output = document.querySelector('#result')!;
const requireClient = () => { if (!client) throw new Error('Synthetic endpoint unavailable.'); return client; };
const api = {
  runtime() { return { sdk: openpgp.config.versionString, secureContext: isSecureContext, subtleCrypto: Boolean(crypto.subtle) }; },
  async generate() { identity = await generateIdentity(); return trustedPeer(identity); },
  async initialize(caseId: string, role: Author, pin: TrustedPeer) {
    if (!identity) throw new Error('Generate the synthetic endpoint first.');
    client = await ProofClient.create(caseId, role, identity, pin);
    currentCase = caseId; currentRole = role;
    return true;
  },
  async send(kind: MessageKind, content: Document['content']) {
    const document = makeDocument(currentCase, currentRole, kind, content);
    const ciphertext = await requireClient().seal(document);
    let wire: Wire | undefined;
    await sendToMockRelay(document, ciphertext, async body => {
      wire = JSON.parse(body) as Wire;
      const response = await fetch('/__synthetic-inbox-proof/relay', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body, cache: 'no-store',
      });
      if (!response.ok) throw new Error('Synthetic relay unavailable.');
    });
    return wire!;
  },
  async receive(wire: Wire, author: Author, kind: MessageKind) {
    output.textContent = 'Verifying.';
    try {
      const document = await requireClient().open(wire.ciphertext, { messageId: wire.message_id, author, kind });
      output.textContent = JSON.stringify(document.content);
      return { accepted: true };
    } catch {
      output.textContent = 'Rejected before display.';
      return { accepted: false };
    }
  },
  async negative(variant: string) {
    if (!identity) throw new Error('No synthetic identity.');
    const original = makeDocument(currentCase, 'contributor', 'submission', { label: 'SYNTHETIC_REJECTED_PLAINTEXT' });
    const changes: Record<string, Record<string, unknown>> = {
      protocol: { protocol: 'wrong-protocol' }, version: { version: 99 },
      case: { caseId: crypto.randomUUID() }, message: { messageId: crypto.randomUUID() },
      author: { author: 'reviewer' }, kind: { kind: 'reply' },
    };
    const bytes = await openpgp.encrypt({
      message: await openpgp.createMessage({ text: JSON.stringify({ ...original, ...changes[variant] }) }),
      encryptionKeys: [identity.publicKey, await openpgp.readKey({ armoredKey: api.peerForNegative })],
      ...(variant !== 'unsigned' ? { signingKeys: identity.privateKey } : {}), format: 'binary',
    });
    if (variant === 'tampered') { const index = bytes.length - 12; bytes[index] = bytes[index]! ^ 1; }
    return { case_id: original.caseId, message_id: original.messageId,
      ciphertext: openpgp.armor(openpgp.enums.armor.message, bytes) as string };
  },
  // Public peer material only; supplied by the test when constructing negative SDK messages.
  peerForNegative: '' as string,
  recovery() { return requireClient().exportRecovery(); },
  async recover(encryptedExport: string, localRecoverySecret: string) {
    try {
      client = await ProofClient.recover(encryptedExport, localRecoverySecret);
      currentCase = client.caseId; currentRole = client.role;
      return true;
    } catch { return false; }
  },
};
declare global { interface Window { syntheticInboxProof: typeof api } }
window.syntheticInboxProof = api;
