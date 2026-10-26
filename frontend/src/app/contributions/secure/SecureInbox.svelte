<script lang="ts">
  import { onMount } from 'svelte';
  import { createSecureCommunityRepository, SecureCommunityError, type SecureInbox as InboxData } from '../../../api/SecureCommunityRepository';
  import { configuredReviewerFingerprint } from '../../../features/contributions/secureInboxMode';
  import { confirmSecureReply, exportSecureRecovery, forgetSecureSession, getSecureSession, prepareSecureReply, rememberSecureSession, restoreSecureSession, secureSessionCredentials, secureTrackingHref, verifySecureInbox, type PreparedSecureReply, type SecureSession, type VerifiedSecureMessage } from '../../../features/contributions/secureInbox';
  import { language, tr } from '../../language';
  import SecureMessages from './SecureMessages.svelte';
  import SecureRecoveryControls from './SecureRecoveryControls.svelte';
  import { displaySecureDate, isSecureAccessFailure, readRecoveryFile, readSecureRoute, secureStatusLabels } from './secureUi';
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  const repository = createSecureCommunityRepository();
  let route = $state.raw<ReturnType<typeof readSecureRoute>>(null), session = $state.raw<SecureSession | null>(null);
  let inbox = $state.raw<InboxData | null>(null), messages = $state.raw<readonly VerifiedSecureMessage[]>([]);
  let busy = $state(false), error = $state(''), recoveryArmor = $state(''), recoveryKey = $state(''), fileReady = $state(false);
  let replyText = $state(''), replyBusy = $state(false), replyError = $state(''), pendingReply = $state.raw<PreparedSecureReply | null>(null);
  let recovery = $state.raw<{ encryptedExport: string; recoverySecret: string } | null>(null);
  let generation = 0, fileGeneration = 0;
  function clearPlaintext() { inbox = null; messages = []; replyText = ''; pendingReply = null; replyError = ''; recovery = null; }
  function forget() {
    if (session) forgetSecureSession(secureSessionCredentials(session).caseId);
    session = null; clearPlaintext();
  }
  async function load() {
    const active = session;
    if (!active) return;
    const request = ++generation, credentials = secureSessionCredentials(active);
    busy = true; error = ''; inbox = null; messages = [];
    try {
      const next = await repository.inbox(credentials.caseId, credentials.accessSecret);
      if (next.status === 'removed') throw new SecureCommunityError('This inbox has been removed.', 404);
      const verified = await verifySecureInbox(next, active);
      if (request !== generation) return;
      inbox = next; messages = verified; rememberSecureSession(active);
    } catch (failure) {
      if (request !== generation) return;
      if (failure instanceof SecureCommunityError && !isSecureAccessFailure(failure)) clearPlaintext();
      else forget();
      error = failure instanceof SecureCommunityError ? failure.message : 'The inbox could not be verified. Reopen it with your recovery file.';
    } finally { if (request === generation) busy = false; }
  }
  function fromRoute() {
    if (!window.location.hash.startsWith('#/secure-inbox')) return;
    generation += 1; session = null; clearPlaintext(); busy = false; error = ''; recoveryKey = ''; recoveryArmor = ''; fileReady = false;
    route = readSecureRoute(window.location.hash);
    if (!route) {
      if (window.location.hash.includes('?')) error = 'This private inbox link is invalid. Use your recovery file.';
      return;
    }
    const remembered = getSecureSession(route.caseId);
    if (!remembered) return;
    const credentials = secureSessionCredentials(remembered);
    if (route.accessSecret && route.accessSecret !== credentials.accessSecret) { forgetSecureSession(route.caseId); error = 'This private inbox link does not match the saved session.'; return; }
    session = remembered; void load();
  }
  async function chooseFile(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    const request = ++fileGeneration;
    try { const value = await readRecoveryFile(file); if (request === fileGeneration) { recoveryArmor = value; fileReady = true; error = ''; } }
    catch { if (request === fileGeneration) { recoveryArmor = ''; fileReady = false; error = 'Choose a readable recovery file smaller than 256 KB.'; } }
  }
  async function recover(event: SubmitEvent) {
    event.preventDefault();
    if (busy || !recoveryArmor || !recoveryKey.trim()) { error = 'Choose your recovery file and enter its recovery key.'; return; }
    const request = ++generation; busy = true; error = ''; clearPlaintext();
    try {
      const candidate = await restoreSecureSession(recoveryArmor, recoveryKey.trim(), configuredReviewerFingerprint());
      if (request !== generation) return;
      const credentials = secureSessionCredentials(candidate);
      if (route && (route.caseId !== credentials.caseId || (route.accessSecret && route.accessSecret !== credentials.accessSecret))) throw new Error();
      session = candidate; route = { caseId: credentials.caseId, accessSecret: credentials.accessSecret };
      window.history.replaceState(null, '', secureTrackingHref(candidate));
      recoveryKey = ''; recoveryArmor = ''; fileReady = false; busy = false;
      await load();
    } catch { if (request === generation) { forget(); error = 'The recovery file, key, or inbox link did not match.'; busy = false; } }
  }
  async function sendReply(event?: SubmitEvent) {
    event?.preventDefault();
    const active = session, activeInbox = inbox;
    if (!active || !activeInbox || activeInbox.status === 'closed' || replyBusy) return;
    if (!pendingReply && !replyText.trim()) { replyError = 'Write a reply before sending.'; return; }
    replyBusy = true; replyError = '';
    try {
      if (!pendingReply) { const prepared = await prepareSecureReply(active, replyText.trim()); if (session !== active) return; pendingReply = prepared; }
      const credentials = secureSessionCredentials(active);
      const sent = pendingReply;
      await repository.reply(credentials.caseId, credentials.accessSecret, sent);
      if (session !== active) return;
      confirmSecureReply(active, sent);
      pendingReply = null; replyText = ''; await load();
    } catch (failure) {
      if (session === active) {
        if (isSecureAccessFailure(failure)) { forget(); error = failure.message; }
        else replyError = failure instanceof SecureCommunityError ? failure.message : 'The reply could not be prepared. Try again.';
      }
    }
    finally { replyBusy = false; }
  }
  async function prepareRecovery() {
    const active = session;
    if (!active) return;
    try { const value = await exportSecureRecovery(active); if (session === active) recovery = value; }
    catch { error = 'Recovery access could not be prepared. Try again.'; }
  }
  function lock() {
    generation += 1; fileGeneration += 1; forget(); busy = false; replyBusy = false; error = ''; recoveryArmor = ''; recoveryKey = ''; fileReady = false;
    if (route) { route = { caseId: route.caseId, accessSecret: '' }; window.history.replaceState(null, '', `#/secure-inbox?case_id=${route.caseId}`); }
  }
  onMount(() => { fromRoute(); return () => { generation += 1; fileGeneration += 1; clearPlaintext(); }; });
</script>
<svelte:window onhashchange={fromRoute} />
<section class="secure-inbox" aria-labelledby="secure-inbox-title">
  <header class="page-heading"><div><p class="local-indicator">{tr('Local experiment', $language)}</p><h1 id="secure-inbox-title">{tr('Your private inbox', $language)}</h1>{#if route}<p class="reference">{tr('Reference', $language)} <span>{route.caseId}</span></p>{/if}</div><a href={`#/contribute${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`}>{tr('Back to Contribute', $language)}</a></header>
  {#if error}<p class="error" role="alert">{tr(error, $language)}</p>{/if}
  {#if busy}<p role="status">{tr('Opening and verifying inbox…', $language)}</p>{/if}
  {#if session && inbox}
    <div class="status-bar"><div><span>{tr('Current processing status', $language)}</span><strong>{tr(secureStatusLabels[inbox.status], $language)}</strong><small>{tr('Updated', $language)} {displaySecureDate(inbox.updated_at)}</small></div><div class="actions"><button type="button" disabled={busy || replyBusy} onclick={() => void load()}>{tr('Refresh inbox', $language)}</button><button type="button" onclick={lock}>{tr('Lock inbox', $language)}</button></div></div>
    <SecureMessages {messages} />
    {#if inbox.status !== 'closed'}<form class="reply-form" onsubmit={sendReply}><label>{tr('Reply to reviewer', $language)}<textarea bind:value={replyText} maxlength="6000" rows="4" readonly={pendingReply !== null} disabled={replyBusy}></textarea></label>{#if replyError}<p class="error" role="alert">{tr(replyError, $language)}</p>{/if}<button class="primary" type="submit" disabled={replyBusy}>{tr(replyBusy ? 'Sending…' : pendingReply ? 'Retry encrypted reply' : 'Send encrypted reply', $language)}</button></form>{:else}<p class="closed-note">{tr('This inbox is closed to new replies.', $language)}</p>{/if}
    {#if recovery}<SecureRecoveryControls encryptedExport={recovery.encryptedExport} recoverySecret={recovery.recoverySecret} caseId={inbox.case_id} />{:else}<button class="recovery-action" type="button" onclick={() => void prepareRecovery()}>{tr('Get recovery file and key', $language)}</button>{/if}
  {:else if session && !busy}
    <div class="actions"><button class="primary" type="button" onclick={() => void load()}>{tr('Retry opening inbox', $language)}</button><button type="button" onclick={lock}>{tr('Lock inbox', $language)}</button></div>
    {#if recovery}<SecureRecoveryControls encryptedExport={recovery.encryptedExport} recoverySecret={recovery.recoverySecret} caseId={session.caseId} />{:else}<button class="recovery-action" type="button" onclick={() => void prepareRecovery()}>{tr('Get recovery file and key', $language)}</button>{/if}
  {:else if !busy}
    <form class="recovery-form" onsubmit={recover}><h2>{tr('Reopen with recovery access', $language)}</h2><label>{tr('Recovery file', $language)}<input type="file" accept=".asc,text/plain" onchange={chooseFile} /></label>{#if fileReady}<p class="file-ready" role="status">{tr('Recovery file ready.', $language)}</p>{/if}<label>{tr('Recovery key', $language)}<input type="password" bind:value={recoveryKey} autocomplete="off" maxlength="512" /></label><button class="primary" type="submit" disabled={busy}>{tr('Open inbox', $language)}</button></form>
  {/if}
</section>
<style>
  .secure-inbox{width:min(100% - 4rem,50rem);margin:0 auto;padding:2rem 0 2.5rem;color:var(--ink);font:.9rem/1.5 system-ui,sans-serif}.page-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;margin-bottom:1.5rem}.local-indicator{margin:0 0 .7rem;font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-muted)}h1{font:400 2.25rem/1.15 Georgia,serif;letter-spacing:-.03em;margin:0 0 .7rem}.reference{font-size:.75rem;color:var(--ink-muted);margin:0}.reference span{display:block;overflow-wrap:anywhere}.page-heading>a{font-size:.8rem;min-height:2.75rem;display:flex;align-items:center;white-space:nowrap;color:var(--ink);text-underline-offset:.25em}.status-bar{display:flex;justify-content:space-between;align-items:center;gap:1rem;padding:1rem 0;border-top:1px solid var(--line)}.status-bar span,.status-bar small{display:block;font-size:.75rem;color:var(--ink-muted)}.status-bar strong{font-size:1rem;font-weight:500}.status-bar small{margin-top:.3rem}.actions{display:flex;flex-wrap:wrap;gap:.6rem}.reply-form,.recovery-form{display:grid;gap:1rem;margin-top:1rem;padding-top:1rem;border-top:1px solid var(--line)}.recovery-form{max-width:36rem}h2{font:400 1.6rem/1.2 Georgia,serif;margin:0 0 .25rem}label{display:grid;gap:.4rem;font-size:.8rem;font-weight:500}input,textarea{min-width:0;width:100%;min-height:2.75rem;padding:.6rem .75rem;background:var(--panel);color:var(--ink);border:1px solid var(--line-strong);border-radius:0;font:400 .9rem/1.5 system-ui,sans-serif}input[type=file]{font-size:.8rem;padding:.5rem}textarea{resize:vertical}button{justify-self:start;min-height:2.75rem;padding:.6rem .85rem;border:1px solid var(--line-strong);background:transparent;color:var(--ink);font:inherit;cursor:pointer}.primary{background:var(--ink);color:var(--page);border-color:var(--ink)}button:disabled{opacity:.6;cursor:wait}.error{font-size:.85rem;padding:.6rem .8rem;border-left:2px solid var(--focus);overflow-wrap:anywhere}.file-ready,.closed-note{color:var(--ink-muted);font-size:.8rem;margin:0}.closed-note{padding:1rem 0;border-top:1px solid var(--line)}.recovery-action{margin-top:1.5rem}:is(a,button,input,textarea):focus-visible{outline:3px solid var(--focus);outline-offset:3px}@media(max-width:38rem){.secure-inbox{width:calc(100% - 2rem);padding-top:1.5rem}.page-heading{gap:.7rem}h1{font-size:1.9rem}.page-heading>a{font-size:.75rem}.status-bar{align-items:flex-start;flex-direction:column}input,textarea{font-size:1rem}}
</style>
