<script lang="ts">
  import { onMount } from 'svelte';
  import { createSecureCommunityRepository, SecureCommunityError, type SecureCaseSummary, type SecureInbox, type SecureStatus } from '../../../api/SecureCommunityRepository';
  import { configuredReviewerFingerprint } from '../../../features/contributions/secureInboxMode';
  import { confirmSecureReply, generateSecureReviewerKey, prepareSecureReply, reviewerSession, unlockSecureReviewerKey, verifySecureInbox, type PreparedSecureReply, type ReviewerKey, type SecureSession, type VerifiedSecureMessage } from '../../../features/contributions/secureInbox';
  import { language, tr } from '../../language';
  import { intakeTitles } from '../contributionForm';
  import SecureMessages from './SecureMessages.svelte';
  import SecureRecoveryControls from './SecureRecoveryControls.svelte';
  import { displaySecureDate, isSecureAccessFailure, readRecoveryFile, secureStatusLabels } from './secureUi';
  const repository = createSecureCommunityRepository();
  let capability = $state<'loading' | 'ready' | 'unavailable'>('loading');
  let operatorToken = $state(''), queue = $state.raw<readonly SecureCaseSummary[] | null>(null), queueBusy = $state(false), queueError = $state('');
  let reviewerKey = $state.raw<ReviewerKey | null>(null), keyArmor = $state(''), recoveryKey = $state(''), fileReady = $state(false), unlockBusy = $state(false), unlockError = $state('');
  let caseId = $state(''), inbox = $state.raw<SecureInbox | null>(null), messages = $state.raw<readonly VerifiedSecureMessage[]>([]), caseBusy = $state(false), caseError = $state('');
  let replyText = $state(''), pendingReply = $state.raw<PreparedSecureReply | null>(null), replyBusy = $state(false), replyError = $state('');
  let changingStatus = $state(false), removeConfirmation = $state(false), notice = $state('');
  let setup = $state.raw<Awaited<ReturnType<typeof generateSecureReviewerKey>> | null>(null), setupBusy = $state(false), setupError = $state(''), publicCopy = $state('');
  const sessions = new Map<string, SecureSession>();
  const replyDrafts = new Map<string, { text: string; pending: PreparedSecureReply | null; error: string }>();
  let queueGeneration = 0, caseGeneration = 0, unlockGeneration = 0, setupGeneration = 0, fileGeneration = 0;
  async function loadCapability() {
    capability = 'loading';
    try { const value = await repository.capabilities(); capability = value.enabled && value.reviewer_fingerprint === configuredReviewerFingerprint() ? 'ready' : 'unavailable'; }
    catch { capability = 'unavailable'; }
  }
  function clearCase() { inbox = null; messages = []; replyText = ''; pendingReply = null; replyError = ''; removeConfirmation = false; }
  async function openQueue(event?: SubmitEvent) {
    event?.preventDefault();
    if (queueBusy || capability !== 'ready') return;
    const request = ++queueGeneration, token = operatorToken;
    queueBusy = true; queueError = ''; notice = '';
    try { const result = await repository.queue(token); if (request === queueGeneration && token === operatorToken) queue = result; }
    catch (error) { if (request === queueGeneration) { if (isSecureAccessFailure(error)) lock(); else { queue = null; clearCase(); } queueError = error instanceof SecureCommunityError ? error.message : 'The review queue is unavailable. Try again.'; } }
    finally { if (request === queueGeneration) queueBusy = false; }
  }
  async function chooseFile(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0]; if (!file) return;
    const request = ++fileGeneration;
    try { const value = await readRecoveryFile(file); if (request === fileGeneration) { keyArmor = value; fileReady = true; unlockError = ''; } }
    catch { if (request === fileGeneration) { keyArmor = ''; fileReady = false; unlockError = 'Choose a readable reviewer key file smaller than 256 KB.'; } }
  }
  async function unlock(event: SubmitEvent) {
    event.preventDefault();
    if (unlockBusy) return;
    if (!keyArmor || !recoveryKey.trim()) { unlockError = 'Choose the encrypted reviewer key file and enter its recovery key.'; return; }
    const request = ++unlockGeneration; unlockBusy = true; unlockError = '';
    try {
      const key = await unlockSecureReviewerKey(keyArmor, recoveryKey.trim(), configuredReviewerFingerprint());
      if (request !== unlockGeneration) return;
      reviewerKey = key; keyArmor = ''; recoveryKey = ''; fileReady = false; sessions.clear(); clearCase();
      if (caseId) await loadCase(caseId);
    } catch { if (request === unlockGeneration) { reviewerKey = null; sessions.clear(); clearCase(); unlockError = 'The reviewer key could not be unlocked or does not match this preview.'; } }
    finally { if (request === unlockGeneration) unlockBusy = false; }
  }
  async function loadCase(id: string) {
    const key = reviewerKey, token = operatorToken;
    if (!key || !token || capability !== 'ready') return;
    const request = ++caseGeneration;
    caseBusy = true; caseError = ''; inbox = null; messages = []; removeConfirmation = false;
    try {
      const next = await repository.reviewerInbox(token, id);
      if (next.status === 'removed') throw new SecureCommunityError('This inbox has been removed.', 404);
      const active = sessions.get(id) ?? await reviewerSession(next, key, configuredReviewerFingerprint());
      const verified = await verifySecureInbox(next, active);
      if (request !== caseGeneration || key !== reviewerKey || token !== operatorToken || id !== caseId) return;
      sessions.set(id, active); inbox = next; messages = verified;
    } catch (error) {
      if (request !== caseGeneration) return;
      if (isSecureAccessFailure(error)) { lock(); queueError = error.message; }
      else { clearCase(); replyDrafts.delete(id); caseError = error instanceof SecureCommunityError ? error.message : 'The messages could not be verified. No submission text is shown.'; }
    } finally { if (request === caseGeneration) caseBusy = false; }
  }
  function chooseCase(id: string) {
    if (replyBusy || changingStatus) return;
    if (caseId) replyDrafts.set(caseId, { text: replyText, pending: pendingReply, error: replyError });
    caseGeneration += 1; clearCase(); caseId = id; caseError = ''; notice = '';
    const saved = replyDrafts.get(id); if (saved) { replyText = saved.text; pendingReply = saved.pending; replyError = saved.error; }
    if (reviewerKey) void loadCase(id);
  }
  async function sendReply(event: SubmitEvent) {
    event.preventDefault();
    const key = reviewerKey, activeInbox = inbox, token = operatorToken, active = sessions.get(caseId), id = caseId;
    if (!key || !activeInbox || !active || replyBusy || activeInbox.status === 'closed') return;
    if (!pendingReply && !replyText.trim()) { replyError = 'Write a reply before sending.'; return; }
    replyBusy = true; replyError = '';
    try {
      if (!pendingReply) { const value = await prepareSecureReply(active, replyText.trim()); if (key !== reviewerKey || id !== caseId) return; pendingReply = value; }
      const sent = pendingReply;
      await repository.reviewerReply(token, id, key.fingerprint, sent);
      if (key !== reviewerKey || id !== caseId) return;
      confirmSecureReply(active, sent);
      pendingReply = null; replyText = ''; replyDrafts.delete(id); await loadCase(id);
    } catch (error) { if (key === reviewerKey && id === caseId) { if (isSecureAccessFailure(error)) { lock(); queueError = error.message; } else replyError = error instanceof SecureCommunityError ? error.message : 'The reply could not be prepared. Try again.'; } }
    finally { replyBusy = false; }
  }
  async function disposition(status: SecureStatus) {
    const key = reviewerKey, id = caseId, token = operatorToken;
    if (!key || !inbox || changingStatus || replyBusy) return;
    changingStatus = true; caseError = ''; notice = '';
    try {
      await repository.disposition(token, id, status);
      if (key !== reviewerKey || id !== caseId) return;
      if (status === 'removed') { caseGeneration += 1; clearCase(); sessions.delete(id); replyDrafts.delete(id); caseId = ''; notice = 'Inbox removed. Contributor access is revoked.'; }
      else await loadCase(id);
      await openQueue();
      if (status === 'removed' && key === reviewerKey) notice = 'Inbox removed. Contributor access is revoked.';
    } catch (error) { if (key === reviewerKey) { if (isSecureAccessFailure(error)) { lock(); queueError = error.message; } else caseError = error instanceof SecureCommunityError ? error.message : 'The status could not be changed. Try again.'; } }
    finally { changingStatus = false; }
  }
  async function generateKey() {
    if (setupBusy) return;
    const request = ++setupGeneration; setupBusy = true; setupError = ''; setup = null; publicCopy = '';
    try { const value = await generateSecureReviewerKey(); if (request === setupGeneration) setup = value; }
    catch { if (request === setupGeneration) setupError = 'The reviewer key could not be generated. Try again.'; }
    finally { if (request === setupGeneration) setupBusy = false; }
  }
  async function copyPublic(value: string) {
    try { if (!navigator.clipboard?.writeText) throw new Error(); await navigator.clipboard.writeText(value); publicCopy = 'Copied'; }
    catch { publicCopy = 'Copy failed. Select and copy the public value manually.'; }
  }
  function lock() {
    queueGeneration += 1; caseGeneration += 1; unlockGeneration += 1; setupGeneration += 1; fileGeneration += 1;
    operatorToken = ''; queue = null; reviewerKey = null; keyArmor = ''; recoveryKey = ''; fileReady = false;
    sessions.clear(); replyDrafts.clear(); clearCase(); caseId = ''; setup = null; publicCopy = ''; notice = '';
    queueError = ''; caseError = ''; unlockError = ''; setupError = ''; queueBusy = false; caseBusy = false; unlockBusy = false; setupBusy = false; replyBusy = false; changingStatus = false;
  }
  onMount(() => { void loadCapability(); return lock; });
</script>
<section class="secure-review" aria-labelledby="secure-review-title">
  <header class="page-heading"><div><p class="local-indicator">{tr('Local experiment', $language)}</p><h1 id="secure-review-title">{tr('Private inbox review', $language)}</h1></div>{#if queue || reviewerKey || setup}<button type="button" onclick={lock}>{tr('Lock review', $language)}</button>{/if}</header>
  {#if capability !== 'ready'}<div class="capability-state"><p role="status">{tr(capability === 'loading' ? 'Checking local inbox configuration…' : 'The local encrypted inbox is unavailable or its key does not match.', $language)}</p>{#if capability === 'unavailable'}<button type="button" onclick={() => void loadCapability()}>{tr('Retry', $language)}</button>{/if}</div>{/if}
  <div class="access-grid">
    {#if !queue}<form onsubmit={openQueue}><h2>{tr('Reviewer access', $language)}</h2><label>{tr('Reviewer access token', $language)}<input type="password" bind:value={operatorToken} maxlength="4096" autocomplete="off" required /></label>{#if queueError}<p class="error" role="alert">{tr(queueError, $language)}</p>{/if}<button class="primary" type="submit" disabled={queueBusy || capability !== 'ready'}>{tr(queueBusy ? 'Opening…' : 'Open review queue', $language)}</button></form>{/if}
    {#if !reviewerKey}<form onsubmit={unlock}><h2>{tr('Unlock reviewer key', $language)}</h2><label>{tr('Encrypted reviewer key file', $language)}<input type="file" accept=".asc,text/plain" onchange={chooseFile} /></label>{#if fileReady}<p class="quiet-note" role="status">{tr('Reviewer key file ready.', $language)}</p>{/if}<label>{tr('Recovery key', $language)}<input type="password" bind:value={recoveryKey} maxlength="512" autocomplete="off" /></label>{#if unlockError}<p class="error" role="alert">{tr(unlockError, $language)}</p>{/if}<button type="submit" disabled={unlockBusy}>{tr(unlockBusy ? 'Unlocking…' : 'Unlock key locally', $language)}</button></form>{/if}
  </div>
  {#if notice}<p class="quiet-note" role="status">{tr(notice, $language)}</p>{/if}
  {#if queue}
    <div class="queue-toolbar"><p>{queue.length} {tr('inboxes shown', $language)}{#if reviewerKey} · {tr('Reviewer key unlocked', $language)}{/if}</p><button type="button" disabled={queueBusy || replyBusy || changingStatus} onclick={() => void openQueue()}>{tr('Refresh queue', $language)}</button></div>
    {#if queueError}<p class="error" role="alert">{tr(queueError, $language)}</p>{/if}
    <div class="review-workspace"><aside aria-label={tr('Review queue', $language)}>{#each queue as item (item.case_id)}<button class="queue-case" type="button" aria-current={caseId === item.case_id ? 'true' : undefined} disabled={replyBusy || changingStatus} onclick={() => chooseCase(item.case_id)}><strong>{tr(intakeTitles[item.kind], $language)}</strong><span>{item.case_id.slice(0,8)} · {tr(secureStatusLabels[item.status], $language)}</span><small>{displaySecureDate(item.updated_at)}</small></button>{:else}<p class="quiet-note">{tr('No inboxes in this queue.', $language)}</p>{/each}</aside><div class="case-pane">
      {#if caseError}<p class="error" role="alert">{tr(caseError, $language)}</p>{/if}
      {#if caseBusy}<p role="status">{tr('Opening and verifying inbox…', $language)}</p>
      {:else if caseId && !reviewerKey}<p class="quiet-note">{tr('Unlock your reviewer key to read this inbox.', $language)}</p>
      {:else if inbox}
        <div class="case-heading"><h2>{tr('Submission inbox', $language)}</h2><p class="reference">{inbox.case_id}</p><p class="processing-status">{tr('Current processing status', $language)}: <strong>{tr(secureStatusLabels[inbox.status], $language)}</strong></p><button type="button" disabled={replyBusy || changingStatus} onclick={() => void loadCase(caseId)}>{tr('Refresh inbox', $language)}</button></div>
        <SecureMessages {messages} />
        {#if inbox.status !== 'closed'}<form class="reply-form" onsubmit={sendReply}><label>{tr('Reply to contributor', $language)}<textarea bind:value={replyText} rows="4" maxlength="6000" readonly={pendingReply !== null} disabled={replyBusy || changingStatus}></textarea></label>{#if replyError}<p class="error" role="alert">{tr(replyError, $language)}</p>{/if}<button class="primary" type="submit" disabled={replyBusy || changingStatus}>{tr(replyBusy ? 'Sending…' : pendingReply ? 'Retry encrypted reply' : 'Send encrypted reply', $language)}</button></form>{:else}<p class="quiet-note">{tr('This inbox is closed to new replies.', $language)}</p>{/if}
        <section class="status-controls" aria-label={tr('Change processing status', $language)}><h3>{tr('Processing status', $language)}</h3><div class="status-actions">{#each ['in_review','needs_information','closed'] as status}<button type="button" disabled={changingStatus || replyBusy} onclick={() => void disposition(status as SecureStatus)}>{tr(secureStatusLabels[status as SecureStatus], $language)}</button>{/each}</div></section>
        <section class="removal"><button class="text-action" type="button" disabled={changingStatus || replyBusy} onclick={() => removeConfirmation = !removeConfirmation}>{tr('Remove this inbox', $language)}</button>{#if removeConfirmation}<p>{tr('Remove the intake and revoke contributor access? This does not change the public map record.', $language)}</p><div class="status-actions"><button type="button" disabled={changingStatus} onclick={() => void disposition('removed')}>{tr('Confirm inbox removal', $language)}</button><button type="button" onclick={() => removeConfirmation = false}>{tr('Cancel', $language)}</button></div>{/if}</section>
      {:else if !caseError}<p class="quiet-note">{tr('Choose an inbox from the queue.', $language)}</p>{/if}
    </div></div>
  {/if}
  <details class="key-setup"><summary>{tr('Set up a local reviewer key', $language)}</summary><p>{tr('Generate a key locally, then configure its public key and fingerprint on the local service.', $language)}</p><button type="button" disabled={setupBusy} onclick={() => void generateKey()}>{tr(setupBusy ? 'Generating…' : 'Generate reviewer key locally', $language)}</button>{#if setupError}<p class="error" role="alert">{tr(setupError, $language)}</p>{/if}{#if setup}<div class="public-configuration"><label>{tr('Public reviewer fingerprint', $language)}<input value={setup.fingerprint} readonly /></label><button type="button" onclick={() => void copyPublic(setup!.fingerprint)}>{tr('Copy public fingerprint', $language)}</button><label>{tr('Public reviewer key', $language)}<textarea value={setup.publicKey} readonly rows="5"></textarea></label><button type="button" onclick={() => void copyPublic(setup!.publicKey)}>{tr('Copy public key', $language)}</button>{#if publicCopy}<p class="quiet-note" role="status">{tr(publicCopy, $language)}</p>{/if}</div><SecureRecoveryControls encryptedExport={setup.encryptedExport} recoverySecret={setup.recoverySecret} reviewer />{/if}</details>
</section>
<style>
  .secure-review{width:min(100% - 4rem,66rem);margin:0 auto;padding:2rem 0 2.5rem;color:var(--ink);font:.9rem/1.5 system-ui,sans-serif}.page-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;margin-bottom:1.5rem}.local-indicator{margin:0 0 .7rem;color:var(--ink-muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.1em}h1{font:400 2.25rem/1.15 Georgia,serif;letter-spacing:-.03em;margin:0}h2{font:400 1.6rem/1.2 Georgia,serif;margin:0 0 .3rem}h3{font-size:.9rem;font-weight:500;margin:0 0 .75rem}.access-grid{display:grid;grid-template-columns:1fr 1fr;gap:2rem;margin-bottom:1.5rem}.access-grid:empty{display:none}form{display:grid;gap:1rem;align-content:start;min-width:0}.access-grid form+form{border-left:1px solid var(--line);padding-left:2rem}label{display:grid;gap:.4rem;font-size:.8rem;font-weight:500}input,textarea{width:100%;min-width:0;min-height:2.75rem;padding:.6rem .75rem;border:1px solid var(--line-strong);border-radius:0;background:var(--panel);color:var(--ink);font:400 .9rem/1.5 system-ui,sans-serif}input[type=file]{font-size:.8rem;padding:.5rem}textarea{resize:vertical}button{justify-self:start;min-height:2.75rem;padding:.6rem .85rem;border:1px solid var(--line-strong);background:transparent;color:var(--ink);font:inherit;cursor:pointer}button:hover{background:var(--panel-hover)}button:disabled{opacity:.6;cursor:wait}.primary{background:var(--ink);color:var(--page);border-color:var(--ink)}.quiet-note{color:var(--ink-muted);font-size:.8rem}.error{font-size:.85rem;padding:.6rem .8rem;border-left:2px solid var(--focus);margin:.5rem 0;overflow-wrap:anywhere}.capability-state{display:flex;gap:1rem;flex-wrap:wrap;align-items:center;margin:0 0 1.5rem;font-size:.8rem;color:var(--ink-muted)}.queue-toolbar{display:flex;justify-content:space-between;gap:1rem;align-items:center;border-block:1px solid var(--line);padding:.8rem 0;margin-bottom:1.3rem}.queue-toolbar p{margin:0;color:var(--ink-muted);font-size:.8rem}.review-workspace{display:grid;grid-template-columns:14rem minmax(0,1fr);gap:2rem}.review-workspace aside{min-width:0}.queue-case{display:block;width:100%;text-align:left;border:1px solid transparent;border-bottom-color:var(--line);padding:.85rem .7rem;min-width:0}.queue-case[aria-current]{background:var(--panel);border-color:var(--line-strong)}.queue-case strong{font-size:.85rem;font-weight:500;display:block}.queue-case span,.queue-case small{display:block;color:var(--ink-muted);font-size:.75rem;margin-top:.25rem;overflow-wrap:anywhere}.case-pane{border-left:1px solid var(--line);padding-left:2rem;min-width:0}.case-heading{margin-bottom:1rem}.reference{font-size:.75rem;color:var(--ink-muted);overflow-wrap:anywhere;margin:.5rem 0}.processing-status{font-size:.8rem;margin:.8rem 0}.processing-status strong{font-weight:500}.reply-form{padding:1rem 0;border-top:1px solid var(--line)}.status-controls{padding-top:1rem;border-top:1px solid var(--line);margin-top:.5rem}.status-actions{display:flex;gap:.6rem;flex-wrap:wrap}.removal{padding-top:.8rem;margin-top:1rem;border-top:1px solid var(--line)}.removal p{font-size:.8rem;color:var(--ink-muted)}.text-action{padding:.4rem 0;background:transparent;border:0;text-decoration:underline;text-underline-offset:.25em}.key-setup{margin-top:2rem;padding-top:1rem;border-top:1px solid var(--line)}summary{min-height:2.75rem;cursor:pointer;font-size:.85rem;padding:.4rem 0}.key-setup>p{font-size:.8rem;color:var(--ink-muted);max-width:42rem}.public-configuration{display:grid;gap:.75rem;margin-top:1.2rem;max-width:48rem}.public-configuration input,.public-configuration textarea{font-family:ui-monospace,monospace;font-size:.8rem;overflow-wrap:anywhere}:is(button,input,textarea,summary):focus-visible{outline:3px solid var(--focus);outline-offset:3px}@media(max-width:46rem){.review-workspace{grid-template-columns:11rem minmax(0,1fr);gap:1.2rem}.case-pane{padding-left:1.2rem}}@media(max-width:38rem){.secure-review{width:calc(100% - 2rem);padding-top:1.5rem}h1{font-size:1.9rem}.access-grid{grid-template-columns:1fr;gap:1.5rem}.access-grid form+form{border-left:0;border-top:1px solid var(--line);padding:1.2rem 0 0}.review-workspace{display:block}.review-workspace aside{margin-bottom:1rem}.case-pane{border-left:0;border-top:1px solid var(--line);padding:1.2rem 0 0}input,textarea{font-size:1rem}.queue-toolbar{align-items:flex-start}.queue-toolbar p{max-width:12rem}}
</style>
