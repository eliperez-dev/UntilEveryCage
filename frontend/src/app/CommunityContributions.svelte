<script lang="ts">
  import { onMount } from 'svelte';
  import { language, tr } from './language';
  import { CommunityError, communityCapabilities, createCommunityRepository, type ContributionKind, type ReviewQueue, type ReviewQueueFilter, type ReviewRow, type CommunityClaims, type CommunityClaim } from '../api/CommunityRepository';
  import { countryName } from './countryOptions';
  import ContributePage from './ContributePage.svelte';
  import ContributionStatus from './contributions/ContributionStatus.svelte';
  let { page, targetRecordId = '', claimId = '', releaseId = '', formKind = 'facility', returnMapHref = '#/map' }: { page: 'form' | 'status' | 'claims' | 'claim-detail' | 'review'; targetRecordId?: string; claimId?: string; releaseId?: string; formKind?: ContributionKind; embedded?: boolean; returnMapHref?: string } = $props();
  const fixtureEnabled = import.meta.env.VITE_COMMUNITY_ENABLED === 'true' || import.meta.env.VITE_COMMUNITY_PILOT === 'true';
  let enabled = $state(fixtureEnabled);
  const repository = createCommunityRepository();
  let busy = $state(false), operatorToken = $state(''), queue = $state<ReviewQueue | null>(null), queueFilter = $state<ReviewQueueFilter>('pending');
  let queueError = $state(''), queueNotice = $state(''), communityRelease = $state(''), claims = $state<CommunityClaims | null>(null), claimsAttempted = $state(false);
  let claim = $state<CommunityClaim | null>(null), communityError = $state('');
  const statusLabel: Record<string, string> = { received: 'Received', held: 'Awaiting review', screened: 'Privacy screened', rejected: 'Not accepted', restricted: 'Restricted', removed: 'Removed', published: 'Published to community submissions' };
  const visitorCopy = (value: string) => value.replaceAll('—', ':');  async function loadQueue() {
    queueError = ''; queueNotice = ''; busy = true;
    try { queue = await repository.queue(operatorToken, 50, queueFilter); }
    catch (error) { queueError = error instanceof CommunityError ? error.message : 'The review queue is unavailable.'; }
    finally { busy = false; }
  }
  async function decide(row: ReviewRow, action: 'hold' | 'screen' | 'reject' | 'restrict' | 'remove') {
    queueNotice = ''; queueError = ''; busy = true;
    const reason_code = action === 'screen' ? 'eligible' : action === 'hold' ? 'other' : action === 'remove' || action === 'restrict' ? 'privacy' : 'out_of_scope';
    try { await repository.disposition(operatorToken, row.submission_id, { action, reason_code }); queueNotice = 'Disposition recorded.'; await loadQueue(); }
    catch (error) { queueError = error instanceof CommunityError ? error.message : 'Disposition could not be recorded.'; }
    finally { busy = false; }
  }
  async function linkCommunity(event: SubmitEvent, row: ReviewRow) {
    event.preventDefault(); queueNotice = ''; queueError = ''; busy = true;
    const values = new FormData(event.currentTarget as HTMLFormElement);
    const community_record_id = String(values.get('community_record_id') ?? '').trim();
    const release_id = String(values.get('release_id') ?? '').trim();
    try {
      await repository.disposition(operatorToken, row.submission_id, { action: 'link_community', reason_code: 'eligible', community_record_id, release_id });
      queueNotice = 'Link recorded to an existing community release. This does not approve curated publication.';
      await loadQueue();
    } catch (error) { queueError = error instanceof CommunityError ? error.message : 'Community release link could not be recorded.'; }
    finally { busy = false; }
  }
  async function loadClaims() {
    communityError = ''; claims = null; claimsAttempted = true; busy = true;
    try {
      const selectedRelease = communityRelease.trim() || releaseId.trim() || await repository.currentCommunityReleaseId();
      communityRelease = selectedRelease;
      claims = await repository.claims(selectedRelease);
    }
    catch { communityError = 'Published community submissions could not be loaded. There may be no active community release.'; }
    finally { busy = false; }
  }
  async function loadClaim() {
    communityError = ''; claim = null; busy = true;
    try { claim = await repository.claim(claimId, releaseId); }
    catch { communityError = 'This published community submission is unavailable.'; }
    finally { busy = false; }
  }
  function openClaim(id: string, releaseId: string) {
    window.location.hash = `#/community/claim?id=${encodeURIComponent(id)}&release_id=${encodeURIComponent(releaseId)}`;
  }
  $effect(() => {
    if (page !== 'review') { operatorToken = ''; queue = null; }
    if (page !== 'claims') { claims = null; claimsAttempted = false; }
    if (page !== 'claim-detail') claim = null;
  });
  $effect(() => { if (page === 'claims' && !claimsAttempted && !claims && !busy) void loadClaims(); });
  onMount(() => { if (!fixtureEnabled) void communityCapabilities().then(value => enabled = value.enabled); });
</script>
<svelte:head><title>{tr(page === 'status' ? 'Contribution status' : page === 'review' ? 'Contribution review' : 'Community claims', $language)} · Until Every Cage</title></svelte:head>
{#if page === 'form'}
  <ContributePage {formKind} {targetRecordId} {returnMapHref} />
{:else if page === 'status'}
  <ContributionStatus {returnMapHref} />
{:else if !enabled && page !== 'claims' && page !== 'claim-detail'}
  <section class="community-unavailable" aria-labelledby="community-title"><h1 id="community-title">Contribute to the project</h1><p>To share a correction, privacy concern, or source, email <a href="mailto:untileverycageproject@protonmail.com">untileverycageproject@protonmail.com</a>. For code contributions, use <a href="https://github.com/UntilEveryCage/UntilEveryCage">GitHub</a>.</p><a href="#/about/sources">Read sources & methodology</a></section>{:else if page === 'review'}
  <section class="community-page" aria-labelledby="community-title"><h1 id="community-title">Contribution review</h1><p class="review-warning"><strong>Private intake warning.</strong> Queue items are untrusted and may contain identifying or harmful information. Open claims only to review them. Privacy screening does not verify facts or approve a curated release.</p>{#if !queue}<form class="contribution-form token-form" onsubmit={(event) => { event.preventDefault(); void loadQueue(); }}><label>Local operator token<input type="password" bind:value={operatorToken} autocomplete="off" required /></label><label>Show submissions<select bind:value={queueFilter}><option value="pending">Pending (received and held)</option><option value="screened">Screened</option><option value="published">Published</option><option value="rejected">Rejected</option><option value="restricted">Restricted</option><option value="removed">Removed</option><option value="received">Received</option><option value="held">Held</option></select></label><button class="primary-action" disabled={busy}>{busy ? 'Loading…' : 'Open restricted queue'}</button></form>{:else}<div class="queue-heading"><p>{queue.pending_count} pending · {queue.submissions.length} shown (page cap: 50)</p><label>Status filter<select bind:value={queueFilter}><option value="pending">Pending (received and held)</option><option value="screened">Screened</option><option value="published">Published</option><option value="rejected">Rejected</option><option value="restricted">Restricted</option><option value="removed">Removed</option><option value="received">Received</option><option value="held">Held</option></select></label><button type="button" disabled={busy} onclick={() => void loadQueue()}>Refresh queue</button><button type="button" onclick={() => { queue = null; operatorToken = ''; }}>Close queue</button></div>{#each queue.submissions as row (row.submission_id)}<article class="queue-item"><p class="eyebrow">{row.kind.replace('_',' ')} · {statusLabel[row.status]} · {new Date(row.created_at).toLocaleDateString()}</p><h2>{row.label ?? (row.kind === 'bug' ? 'Bug report' : 'Unlabelled claim')}</h2>{#if row.country_code || row.locality}<p>{row.country_code ? countryName(row.country_code) : 'Country not supplied'}{#if row.locality} · {row.locality}{/if}</p>{/if}{#if row.claimed_activity}<p>Claimed activity: {row.claimed_activity}</p>{/if}{#if row.observed_on}<p>Observed on: {row.observed_on}</p>{/if}{#if row.target_record_id}<p>Target record: <code>{row.target_record_id}</code></p>{/if}{#if row.duplicate_record_id}<p>Possible duplicate record: <code>{row.duplicate_record_id}</code></p>{/if}{#if row.location_text}<p>Contributor location text: {row.location_text}</p>{/if}{#if row.claimed_precision}<p>Location detail: {row.claimed_precision}</p>{/if}{#if row.location_input_method}<p>Location entered using: {row.location_input_method === 'manual_pin' ? 'map pin' : row.location_input_method === 'text' ? 'typed coordinates or text' : 'other'}</p>{/if}{#if row.description}<p>{row.description}</p>{/if}{#if row.expected_behavior}<p>Expected: {row.expected_behavior}</p>{/if}{#if row.reproduction_steps}<p>Steps to reproduce: {row.reproduction_steps}</p>{/if}{#if row.page_url}<p><a href={row.page_url} target="_blank" rel="noreferrer">Reported page</a></p>{/if}{#if row.source_url}<p><a href={row.source_url} rel="noreferrer" target="_blank">Open submitted source</a></p>{/if}{#if row.claimed_latitude !== undefined}<p>Suggested location · {row.claimed_latitude}, {row.claimed_longitude} (not verified)</p>{/if}<div class="decision-actions"><button disabled={busy} onclick={() => decide(row,'hold')}>Hold</button><button disabled={busy} onclick={() => decide(row,'screen')}>Privacy screen only</button><button disabled={busy} onclick={() => decide(row,'reject')}>Reject submission</button><button disabled={busy} onclick={() => decide(row,'restrict')}>Restrict submission</button><button disabled={busy} onclick={() => decide(row,'remove')}>Remove submission</button></div>{#if row.status === 'screened' && row.kind !== 'privacy_removal'}<details class="link-community"><summary>Link to an existing community release record</summary><p>Only link a source-record ID that already belongs to a screened community release. This does not change the public profile or approve curated publication.</p><form onsubmit={(event) => linkCommunity(event,row)}><label>Existing source-record ID<input name="community_record_id" maxlength="36" required /></label><label>Community release ID<input name="release_id" maxlength="160" required /></label><button disabled={busy}>Record link</button></form></details>{/if}</article>{:else}<p class="quiet-note">No items are currently in this page.</p>{/each}{/if}{#if queueError}<p role="alert" class="form-error">{queueError}</p>{/if}{#if queueNotice}<p role="status">{queueNotice}</p>{/if}<p class="quiet-note">Disposition reasons use a fixed category. Never copy identifying claim text into a public note.</p></section>
{:else if page === 'claims'}
  <section class="community-page" aria-labelledby="community-title"><p class="eyebrow">Explicit opt-in profile</p><h1 id="community-title">Published community submissions</h1><p class="review-warning"><strong>Unreviewed community claim: not verified by Until Every Cage.</strong> This profile contains only submissions that passed privacy screening. Screening is not factual review or project approval. Its counts are separate from curated totals.</p>{#if busy && !claims}<p role="status">Loading published community submissions…</p>{:else if claims}<p class="eyebrow">{claims.claim_count} published submissions · separate profile count</p><p>{visitorCopy(claims.warning)}</p>{#each claims.claims as item (item.submission_id)}<button class="claim-row" onclick={() => openClaim(item.submission_id,item.release_id)}><strong>{item.kind.replace('_',' ')}</strong><span>Community-submitted · unreviewed · not project-approved</span><span>Open claim →</span></button>{:else}<p class="quiet-note">No privacy-screened submissions are published in the current community release.</p>{/each}{/if}{#if communityError}<p role="alert" class="quiet-note">{communityError}</p>{/if}</section>
{:else}
  <section class="community-page narrow" aria-labelledby="community-title"><p class="eyebrow">Explicit opt-in profile</p><h1 id="community-title">Community claim</h1><p class="review-warning"><strong>Unreviewed community claim: not verified by Until Every Cage.</strong> This claim has not completed factual review and is not project-approved.</p><button class="primary-action" disabled={busy} onclick={() => void loadClaim()}>{busy ? 'Loading…' : 'Load this claim'}</button>{#if claim}<section class="claim-detail"><p class="eyebrow">Community-submitted · {claim.kind.replace('_',' ')}</p><p>Factual review: unreviewed</p><p>Project approval: not approved</p><p>{visitorCopy(claim.warning)}</p><a href={claim.public_record_url} target="_blank" rel="noreferrer">View released record data (JSON)</a></section>{/if}{#if communityError}<p role="alert" class="form-error">{communityError}</p>{/if}</section>
{/if}

<style>
  .community-page{color:var(--ink);max-width:48rem;margin:0 auto;padding:1.5rem 1rem 2.5rem;font:.9rem/1.5 system-ui,sans-serif}.community-page.narrow{max-width:42rem}.community-page h1{margin:.15rem 0 .75rem;font:400 clamp(1.65rem,4vw,2rem)/1.15 Georgia,serif;letter-spacing:-.025em}.community-page h2{font:500 1.1rem/1.25 Georgia,serif}.community-page a{color:var(--ink);text-underline-offset:.2em}.eyebrow{margin:0 0 .4rem;color:var(--ink-muted);font-size:.7rem;letter-spacing:.08em;text-transform:uppercase}.contribution-form{display:grid;gap:.8rem;margin-top:.75rem}.contribution-form label{display:grid;gap:.4rem;font-size:.85rem}.contribution-form input,.contribution-form select{width:100%;min-height:2.75rem;padding:.55rem .65rem;border:1px solid var(--line-strong);border-radius:0;background:var(--panel);color:var(--ink);font:inherit}.primary-action{min-height:2.75rem;padding:.6rem 1rem;width:max-content;max-width:100%;background:var(--ink);color:var(--page);border:1px solid var(--ink);font:inherit;cursor:pointer}.primary-action:disabled{opacity:.6;cursor:wait}.quiet-note{color:var(--ink-muted);font-size:.8rem}.form-error{padding:.65rem .8rem;border-left:2px solid var(--focus);color:var(--ink)}.review-warning{max-width:50rem;margin:1.2rem 0;padding:.8rem 1rem;border-left:2px solid var(--line-strong);background:var(--panel);color:var(--ink-secondary)}.token-form{max-width:37rem}.queue-heading{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem;margin:1.2rem 0}.queue-heading button,.decision-actions button,.link-community button{min-height:2.75rem;padding:.5rem .7rem;border:1px solid var(--line-strong);background:var(--panel);color:var(--ink);font:inherit;cursor:pointer}.link-community{margin-top:1rem;padding:.75rem 0;border-top:1px solid var(--line)}.link-community summary{cursor:pointer;min-height:2.75rem}.link-community p{color:var(--ink-muted);font-size:.8rem}.link-community form{display:grid;grid-template-columns:1fr 1fr;gap:.7rem;align-items:end}.link-community label{display:grid;gap:.3rem;color:var(--ink);font-size:.8rem}.link-community input{min-height:2.75rem;width:100%;padding:.5rem;border:1px solid var(--line-strong);background:var(--panel);color:var(--ink);font:inherit}.queue-item{margin:1rem 0;padding:1rem 0;border-top:1px solid var(--line)}.queue-item h2{margin:.2rem 0}.queue-item p{overflow-wrap:anywhere}.queue-item code{font-size:.8rem}.decision-actions{display:flex;flex-wrap:wrap;gap:.45rem;margin-top:1rem}.decision-actions button:hover,.queue-heading button:hover{background:var(--panel-hover)}.claim-row{display:grid;width:100%;gap:.25rem;padding:1rem .25rem;min-height:2.75rem;border:0;border-top:1px solid var(--line);background:transparent;color:var(--ink);text-align:left;cursor:pointer}.claim-row span{color:var(--ink-muted);font-size:.8rem}.claim-detail{padding:1rem 0;border-top:1px solid var(--line);margin-top:1rem}.community-unavailable{max-width:46rem;margin:1rem auto;padding:.75rem 1rem;color:var(--ink);font:1rem/1.5 system-ui,sans-serif}.community-unavailable h1{font:400 2rem Georgia,serif}.community-unavailable p{max-width:38rem;color:var(--ink-secondary);overflow-wrap:anywhere}.community-unavailable a{color:var(--ink)}:is(button,a,input,select,summary):focus-visible{outline:3px solid var(--focus);outline-offset:3px}@media(max-width:38rem){.queue-heading{align-items:flex-start;flex-direction:column}.link-community form{grid-template-columns:1fr}.community-page{padding-top:1.3rem}.contribution-form input,.link-community input{font-size:1rem}}
</style>
