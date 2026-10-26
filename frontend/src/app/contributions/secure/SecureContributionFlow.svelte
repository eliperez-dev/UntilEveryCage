<script lang="ts">
  import { onMount } from 'svelte';
  import type { ContributionDraft, SubmissionKind } from '../../../api/CommunityRepository';
  import { createSecureCommunityRepository, SecureCommunityError, type SecureCapabilities, type SecureReceipt } from '../../../api/SecureCommunityRepository';
  import { configuredReviewerFingerprint } from '../../../features/contributions/secureInboxMode';
  import { prepareSecureSubmission, rememberSecureSession, secureSessionCredentials, secureTrackingHref, type PreparedSecureSubmission } from '../../../features/contributions/secureInbox';
  import { language, tr } from '../../language';
  import ContributionForm from '../ContributionForm.svelte';
  import { emptyIntakeDraft, type IntakeDraft } from '../contributionForm';
  import SecureRecoveryControls from './SecureRecoveryControls.svelte';
  import { secureStatusLabels } from './secureUi';
  let { kind, draft = $bindable(emptyIntakeDraft()), targetRecordId = '', returnMapHref = '#/map', onbusychange }: { kind: SubmissionKind; draft?: IntakeDraft; targetRecordId?: string; returnMapHref?: string; onbusychange?(busy: boolean): void } = $props();
  type Attempt = Readonly<{ prepared: PreparedSecureSubmission; receipt: SecureReceipt | null; sending: boolean; error: string }>;
  let attempts = $state.raw<Partial<Record<SubmissionKind, Attempt>>>({});
  let capabilities = $state.raw<SecureCapabilities | null>(null), loading = $state(true), unavailable = $state('');
  const repository = createSecureCommunityRepository();
  const current = $derived(attempts[kind]);
  async function load() {
    loading = true; unavailable = ''; capabilities = null;
    try {
      const value = await repository.capabilities();
      const expected = configuredReviewerFingerprint();
      if (!value.enabled || !expected || value.reviewer_fingerprint !== expected) throw new Error();
      capabilities = value;
    } catch { unavailable = 'This local encrypted inbox is unavailable or its reviewer key does not match.'; }
    finally { loading = false; }
  }
  function update(kind: SubmissionKind, attempt: Attempt) { attempts = { ...attempts, [kind]: attempt }; }
  async function send(attemptKind: SubmissionKind) {
    const attempt = attempts[attemptKind];
    if (!attempt || attempt.sending || attempt.receipt) return;
    update(attemptKind, { ...attempt, sending: true, error: '' }); onbusychange?.(true);
    try {
      const receipt = await repository.submit(attempt.prepared.request);
      rememberSecureSession(attempt.prepared.session);
      update(attemptKind, { ...attempt, sending: false, receipt, error: '' });
      if (kind === attemptKind) draft = emptyIntakeDraft();
    } catch (error) {
      update(attemptKind, { ...attempt, sending: false, error: error instanceof SecureCommunityError ? error.message : 'The encrypted submission could not be confirmed. Retry this attempt.' });
    } finally { onbusychange?.(false); }
  }
  async function submit(payload: ContributionDraft) {
    const attemptKind = payload.kind, capability = capabilities;
    if (!capability?.enabled || unavailable) throw new Error('Encrypted intake unavailable');
    if (!attempts[attemptKind]) {
      const prepared = await prepareSecureSubmission(payload, capability, configuredReviewerFingerprint());
      update(attemptKind, { prepared, receipt: null, sending: false, error: '' });
    }
    await send(attemptKind);
  }
  onMount(() => { void load(); });
</script>
<section class="secure-flow" aria-label={tr('Local encrypted contribution', $language)}>
  <p class="local-indicator">{tr('Local experiment', $language)}</p>
  {#if current}
    {@const credentials = secureSessionCredentials(current.prepared.session)}
    {#if current.receipt}
      <section class="secure-receipt" aria-labelledby="secure-receipt-heading"><h2 id="secure-receipt-heading">{tr('Submission received', $language)}</h2><p>{tr('Current processing status', $language)}: {tr(secureStatusLabels[current.receipt.status], $language)}</p><p class="reference">{tr('Reference', $language)} <span>{current.receipt.case_id}</span></p><a class="primary" href={secureTrackingHref(current.prepared.session)}>{tr('Open private inbox', $language)} <span aria-hidden="true">→</span></a><SecureRecoveryControls encryptedExport={current.prepared.recovery.encryptedExport} recoverySecret={current.prepared.recovery.recoverySecret} caseId={credentials.caseId} /></section>
    {:else}
      <h2>{tr(current.sending ? 'Sending encrypted submission…' : 'Submission not confirmed', $language)}</h2><p class="pending-copy">{tr('Retry sends the same encrypted message.', $language)}</p><p class="reference">{tr('Reference', $language)} <span>{credentials.caseId}</span></p>{#if current.error}<p class="error" role="alert">{tr(current.error, $language)}</p>{/if}<button class="primary" type="button" disabled={current.sending} onclick={() => void send(kind)}>{tr(current.sending ? 'Sending…' : 'Retry encrypted submission', $language)}</button>
    {/if}
  {:else if loading}<p role="status">{tr('Opening local encrypted intake…', $language)}</p>
  {:else if unavailable}<h2>{tr('Encrypted intake unavailable', $language)}</h2><p class="error" role="alert">{tr(unavailable, $language)}</p><button type="button" onclick={() => void load()}>{tr('Retry', $language)}</button>
  {:else}<ContributionForm {kind} bind:draft {targetRecordId} {returnMapHref} submitOverride={submit} onbusychange={value => onbusychange?.(value)} />{/if}
</section>
<style>
  .secure-flow{color:var(--ink);font:.9rem/1.5 system-ui,sans-serif;min-width:0}.local-indicator{color:var(--ink-muted);font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;margin:0 0 1rem}h2{font:400 clamp(1.6rem,4vw,2rem)/1.2 Georgia,serif;margin:0 0 .8rem}.secure-receipt>p,.pending-copy{color:var(--ink-muted);font-size:.85rem}.reference{font-size:.8rem;margin:1.2rem 0}.reference span{display:block;color:var(--ink);overflow-wrap:anywhere;margin-top:.3rem}.primary,button{display:inline-flex;align-items:center;justify-content:center;min-height:2.75rem;padding:.6rem .9rem;border:1px solid var(--line-strong);color:var(--ink);background:transparent;font:inherit;text-decoration:none;cursor:pointer}.primary{background:var(--ink);color:var(--page);border-color:var(--ink)}button:disabled{opacity:.6;cursor:wait}.error{font-size:.85rem;border-left:2px solid var(--focus);padding:.6rem .8rem;margin:1rem 0;overflow-wrap:anywhere}:is(a,button):focus-visible{outline:3px solid var(--focus);outline-offset:3px}
</style>
