<script lang="ts">
  import { CommunityError, createCommunityRepository, type ContributionKind, type ContributionDraft, type Receipt, type StatusResult, type ReviewQueue, type ReviewQueueFilter, type ReviewRow, type CommunityClaims, type CommunityClaim } from '../api/CommunityRepository';
  import CopyValue from './CopyValue.svelte';
  import ContributionPinPicker from './ContributionPinPicker.svelte';
  import { countryName, countryOptions } from './countryOptions';
  import { parseRecordReference } from './recordReference';

  let { page, targetRecordId = '', claimId = '', releaseId = '', formKind = 'facility', embedded = false, returnMapHref = '#/map' }: { page: 'form' | 'status' | 'claims' | 'claim-detail' | 'review'; targetRecordId?: string; claimId?: string; releaseId?: string; formKind?: ContributionKind; embedded?: boolean; returnMapHref?: string } = $props();
  const enabled = import.meta.env.VITE_COMMUNITY_PILOT === 'true';
  const repository = createCommunityRepository();
  let kind = $state<ContributionKind>('facility');
  let sourceUrlValue = $state('');
  let descriptionValue = $state('');
  let lat = $state<number | undefined>();
  let lon = $state<number | undefined>();
  let precision = $state<'unknown' | 'exact' | 'coarse' | 'unmapped'>('unknown');
  let locationInputMethod = $state<'manual_pin' | 'text' | undefined>();
  let receipt = $state<Receipt | null>(null);
  let submitError = $state('');
  let busy = $state(false);
  let statusId = $state('');
  let receiptSecret = $state('');
  let statusResult = $state<StatusResult | null>(null);
  let statusMessage = $state('');
  let operatorToken = $state('');
  let queue = $state<ReviewQueue | null>(null);
  let queueFilter = $state<ReviewQueueFilter>('pending');
  let queueError = $state('');
  let queueNotice = $state('');
  let communityRelease = $state('');
  let claims = $state<CommunityClaims | null>(null);
  let claim = $state<CommunityClaim | null>(null);
  let communityError = $state('');
  $effect(() => {
    if (page === 'form' && kind !== formKind) {
      kind = formKind; receipt = null; sourceUrlValue = ''; descriptionValue = '';
      lat = undefined; lon = undefined; locationInputMethod = undefined; precision = 'unknown';
    }
  });
  $effect(() => { if (!['facility', 'correction'].includes(kind)) { lat = undefined; lon = undefined; locationInputMethod = undefined; } });

  function field(form: HTMLFormElement, name: string): string {
    const value = new FormData(form).get(name);
    return typeof value === 'string' ? value.trim() : '';
  }
  function optional(value: string): string | undefined { return value || undefined; }
  async function submit(event: SubmitEvent) {
    event.preventDefault(); submitError = ''; receipt = null;
    const form = event.currentTarget as HTMLFormElement;
    const targetValue = field(form, 'target_record_id');
    const target = parseRecordReference(targetValue || targetRecordId);
    if (['evidence','correction','duplicate','privacy_removal'].includes(kind) && !target) { submitError = 'Enter the record link or ID from the record details.'; return; }
    const source = field(form, 'source_url');
    let sourceUrl: string | undefined;
    if (source) {
      try { const parsed = new URL(source); if (!['https:', 'http:'].includes(parsed.protocol) || parsed.username || parsed.password) throw new Error(); sourceUrl = parsed.toString(); }
      catch { submitError = 'Enter a source link without embedded credentials.'; return; }
    }
    const draft: ContributionDraft = {
      kind, consent: true,
      ...(optional(field(form, 'contact_email')) ? { contact_email: field(form, 'contact_email') } : {}),
      ...(target ? { target_record_id: target } : {}),
      ...(optional(field(form, 'duplicate_record_id')) ? { duplicate_record_id: field(form, 'duplicate_record_id') } : {}),
      ...(optional(field(form, 'label')) ? { label: field(form, 'label') } : {}),
      ...(optional(field(form, 'country_code')) ? { country_code: field(form, 'country_code').toUpperCase() } : {}),
      ...(optional(field(form, 'locality')) ? { locality: field(form, 'locality') } : {}),
      ...(optional(field(form, 'claimed_activity')) ? { claimed_activity: field(form, 'claimed_activity') } : {}),
      ...(optional(field(form, 'location_text')) ? { location_text: field(form, 'location_text') } : {}),
      ...(['facility', 'correction'].includes(kind) ? { claimed_precision: precision } : {}),
      ...(['facility', 'correction'].includes(kind) && lat !== undefined && lon !== undefined ? { claimed_latitude: lat, claimed_longitude: lon } : {}),
      ...(['facility', 'correction'].includes(kind) && precision !== 'unmapped' && locationInputMethod !== 'manual_pin' && lat === undefined && lon === undefined && field(form, 'location_text') ? { location_input_method: 'text' as const } : {}),
      ...(['facility', 'correction'].includes(kind) && lat !== undefined && lon !== undefined && locationInputMethod ? { location_input_method: locationInputMethod } : {}),
      ...(sourceUrl ? { source_url: sourceUrl } : {}),
      ...(optional(field(form, 'observed_on')) ? { observed_on: field(form, 'observed_on') } : {}),
      ...(optional(field(form, 'description')) ? { description: field(form, 'description') } : {}),
    };
    busy = true;
    try { receipt = await repository.submit(draft); form.reset(); lat = undefined; lon = undefined; locationInputMethod = undefined; sourceUrlValue = ''; descriptionValue = ''; kind = formKind; }
    catch (error) { submitError = error instanceof CommunityError ? error.message : 'Your contribution could not be sent.'; }
    finally { busy = false; }
  }
  async function checkStatus(event: SubmitEvent) {
    event.preventDefault(); statusMessage = ''; statusResult = null; busy = true;
    try { statusResult = await repository.status(statusId.trim(), receiptSecret.trim()); }
    catch (error) { statusMessage = error instanceof CommunityError ? error.message : 'Status could not be checked.'; }
    finally { busy = false; }
  }
  async function loadQueue() {
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
    communityError = ''; claims = null; busy = true;
    try {
      const releaseId = communityRelease.trim() || await repository.currentCommunityReleaseId();
      communityRelease = releaseId;
      claims = await repository.claims(releaseId);
    }
    catch (error) { communityError = error instanceof CommunityError ? error.message : 'The community profile is unavailable.'; }
    finally { busy = false; }
  }
  async function loadClaim() {
    communityError = ''; claim = null; busy = true;
    try { claim = await repository.claim(claimId, releaseId); }
    catch (error) { communityError = error instanceof CommunityError ? error.message : 'This community claim is unavailable.'; }
    finally { busy = false; }
  }
  function openClaim(id: string, releaseId: string) {
    window.location.hash = `#/community/claim?id=${encodeURIComponent(id)}&release_id=${encodeURIComponent(releaseId)}`;
  }
  function statusClaimHref(result: StatusResult): string | undefined {
    if (!result.public_record_url) return undefined;
    const url = new URL(result.public_record_url, window.location.origin);
    const releaseId = url.searchParams.get('release_id');
    const recordId = url.pathname.match(/^\/api\/v2\/locations\/([0-9a-f-]{36})$/i)?.[1];
    return releaseId && recordId ? `#/community/claim?id=${encodeURIComponent(result.submission_id)}&release_id=${encodeURIComponent(releaseId)}` : undefined;
  }
  function setPrecision(value: 'unknown' | 'exact' | 'coarse' | 'unmapped') {
    precision = value;
    if (value === 'unmapped') { lat = undefined; lon = undefined; locationInputMethod = undefined; }
    else if (lat === undefined && lon === undefined) locationInputMethod = 'text';
  }
  const statusLabel: Record<string, string> = { received: 'Received', held: 'Awaiting review', screened: 'Privacy screened', rejected: 'Not accepted', restricted: 'Restricted', removed: 'Removed', published: 'Published to community submissions' };
  const statusMeaning: Record<string, string> = { received: 'Your contribution is waiting for review.', held: 'A maintainer needs to review this contribution.', screened: 'Privacy screening is complete. This does not verify the facts or approve publication.', rejected: 'This contribution will not be published.', restricted: 'Access is restricted while a concern is addressed.', removed: 'This contribution is no longer available.', published: 'Your contribution was published as an unreviewed community claim, separate from the curated release.' };
  $effect(() => {
    if (page !== 'form') receipt = null;
    if (page !== 'status') { statusId = ''; receiptSecret = ''; statusResult = null; }
    if (page !== 'review') { operatorToken = ''; queue = null; }
    if (page !== 'claims') claims = null;
    if (page !== 'claim-detail') claim = null;
  });
</script>

<svelte:head><title>{page === 'form' ? ({ facility: 'Add a facility', evidence: 'Add evidence', correction: 'Suggest a correction', duplicate: 'Possible duplicate', privacy_removal: 'Privacy review' }[kind]) : page === 'status' ? 'Contribution status' : page === 'review' ? 'Contribution review' : 'Community claims'} — Until Every Cage</title></svelte:head>

{#if !enabled}
  <section class="community-unavailable" aria-labelledby="community-title">{#if embedded}<h2 id="community-title">Contribution forms aren’t available here</h2>{:else}<h1 id="community-title">Contribution forms aren’t available here</h1>{/if}<p>For a correction or privacy concern, email <a href="mailto:untileverycageproject@protonmail.com">untileverycageproject@protonmail.com</a>.</p><a href="#/about/sources">Read sources & methodology</a></section>
{:else if page === 'form'}
  <section class="community-page" class:embedded aria-label="Contribution form">
    {#if !embedded}<p><a href={`#/contribute${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`}>Contribute</a></p><h1 id="community-title">{{ facility: 'Add a facility', evidence: 'Add evidence', correction: 'Suggest a correction', duplicate: 'Report a possible duplicate', privacy_removal: 'Request a privacy review' }[kind]}</h1>{/if}
    <p class="lede">{kind === 'evidence' ? 'Add evidence to an existing record. Your submission will be reviewed.' : 'We review submissions before anything is published.'}</p>
    {#if receipt}
      <section class="receipt" aria-labelledby="receipt-heading"><h2 id="receipt-heading">Contribution received</h2><p>Save both values to check status. The Submission ID identifies your contribution; it is different from a facility’s Record ID. The private receipt lets you check its status.</p><CopyValue label="Submission ID" value={receipt.submission_id} showValue /><CopyValue label="Private receipt" value={receipt.receipt_secret} showValue /><p class="quiet-note">These values are shown once. Lost receipts cannot be recovered.</p><a class="button-link" href={`#/contribution-status${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`}>Check contribution status</a></section>
    {:else}
      <form class="contribution-form" onsubmit={submit}>
        {#if ['evidence','correction','duplicate','privacy_removal'].includes(kind)}<label>{kind === 'evidence' ? 'Record link or ID' : 'Record ID'}<input name="target_record_id" value={parseRecordReference(targetRecordId)} maxlength={kind === 'evidence' ? 1000 : 36} autocomplete="off" required aria-describedby={kind === 'evidence' ? 'evidence-record-help' : undefined} /></label>{/if}
        {#if kind === 'evidence'}<p id="evidence-record-help" class="field-help">Open a record and copy its page link or Record ID.</p>{/if}
        {#if kind === 'duplicate'}<label>Possible duplicate record ID<input name="duplicate_record_id" maxlength="36" autocomplete="off" required /></label>{/if}
        {#if kind === 'facility'}<div class="form-grid"><label>Facility name<input name="label" maxlength="160" required /></label><label>Country (optional)<select name="country_code"><option value="">Unknown / not sure</option>{#each countryOptions as country (country.code)}<option value={country.code}>{country.name}</option>{/each}</select></label></div><div class="form-grid"><label>Locality (optional)<input name="locality" maxlength="160" /></label><label>Activity (optional)<input name="claimed_activity" maxlength="160" /></label></div>{/if}
        {#if kind === 'facility' || kind === 'correction'}
          <fieldset class="location-picker"><legend>Location (optional)</legend>
            <ContributionPinPicker latitude={lat} longitude={lon} onpoint={(latitude, longitude, method) => { lat = latitude; lon = longitude; locationInputMethod = method; }} onclear={() => { lat = undefined; lon = undefined; locationInputMethod = undefined; }} />
            <label>Location detail<select value={precision} onchange={(event) => setPrecision(event.currentTarget.value as 'unknown' | 'exact' | 'coarse' | 'unmapped')}><option value="unknown">Not sure</option><option value="exact">Exact point</option><option value="coarse">Around this area</option><option value="unmapped">No point</option></select></label>
            <label>Location note (optional)<input name="location_text" maxlength="1000" placeholder="City or broad area" /></label>
          </fieldset>
        {/if}
        <label>Source link (optional)<input bind:value={sourceUrlValue} name="source_url" type="url" maxlength="2048" placeholder="https://…" /></label>
        {#if kind === 'facility' || kind === 'evidence'}<label>When did you observe this? (optional)<input name="observed_on" type="date" /></label>{/if}
        {#if kind === 'correction' || kind === 'privacy_removal'}<label>{kind === 'correction' ? 'What should be corrected?' : 'What should we review?'}<textarea bind:value={descriptionValue} name="description" maxlength="2000" rows="4" required></textarea></label>{:else if kind === 'evidence'}<label>What did you find? (optional if you added a source link)<textarea bind:value={descriptionValue} name="description" maxlength="2000" rows="4" required={!sourceUrlValue.trim()}></textarea></label>{:else if kind === 'facility'}<label>Additional context (optional)<textarea bind:value={descriptionValue} name="description" maxlength="2000" rows="4"></textarea></label>{/if}
        <label>Email (optional)<input name="contact_email" type="email" maxlength="254" autocomplete="email" aria-describedby="contact-help" /></label>
        <p id="contact-help" class="field-help">For follow-up about this contribution. Automatic updates are not available yet.</p>
        <label class="consent"><input type="checkbox" required /> I have permission to share this information.</label>
        {#if submitError}<p class="form-error" role="alert">{submitError}</p>{/if}
        <button class="primary-action" type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send for review'}</button>
      </form>
    {/if}
  </section>
{:else if page === 'status'}
  <section class="community-page narrow" aria-labelledby="community-title"><h1 id="community-title">Check contribution status</h1><p class="lede">Enter your Submission ID and private receipt. A Record ID is not a Submission ID.</p><form class="contribution-form" onsubmit={checkStatus}><label>Submission ID<input bind:value={statusId} autocomplete="off" required /></label><label>Private receipt<input bind:value={receiptSecret} autocomplete="off" required /></label><button class="primary-action" disabled={busy}>{busy ? 'Checking…' : 'Check status'}</button></form>{#if statusMessage}<p role="alert" class="form-error">{statusMessage}</p>{/if}{#if statusResult}<section class="status-result" aria-live="polite"><h2>{statusLabel[statusResult.status]}</h2><p>{statusMeaning[statusResult.status]}</p>{#if statusClaimHref(statusResult)}<a href={statusClaimHref(statusResult)}>Open the claim details</a>{:else if statusResult.status === 'published'}<p>No public link is currently available.</p>{/if}</section>{/if}<p class="quiet-note">Lost receipts cannot be recovered. For a separate question, email the project.</p></section>
{:else if page === 'review'}
  <section class="community-page" aria-labelledby="community-title"><h1 id="community-title">Contribution review</h1><p class="review-warning"><strong>Private intake warning.</strong> Queue items are untrusted and may contain identifying or harmful information. Open claims only to review them. Privacy screening does not verify facts or approve a curated release.</p>{#if !queue}<form class="contribution-form token-form" onsubmit={(event) => { event.preventDefault(); void loadQueue(); }}><label>Local operator token<input type="password" bind:value={operatorToken} autocomplete="off" required /></label><label>Show submissions<select bind:value={queueFilter}><option value="pending">Pending (received and held)</option><option value="screened">Screened</option><option value="published">Published</option><option value="rejected">Rejected</option><option value="restricted">Restricted</option><option value="removed">Removed</option><option value="received">Received</option><option value="held">Held</option></select></label><button class="primary-action" disabled={busy}>{busy ? 'Loading…' : 'Open restricted queue'}</button></form>{:else}<div class="queue-heading"><p>{queue.pending_count} pending · {queue.submissions.length} shown (page cap: 50)</p><label>Status filter<select bind:value={queueFilter}><option value="pending">Pending (received and held)</option><option value="screened">Screened</option><option value="published">Published</option><option value="rejected">Rejected</option><option value="restricted">Restricted</option><option value="removed">Removed</option><option value="received">Received</option><option value="held">Held</option></select></label><button type="button" disabled={busy} onclick={() => void loadQueue()}>Refresh queue</button><button type="button" onclick={() => { queue = null; operatorToken = ''; }}>Close queue</button></div>{#each queue.submissions as row (row.submission_id)}<article class="queue-item"><p class="eyebrow">{row.kind.replace('_',' ')} · {statusLabel[row.status]} · {new Date(row.created_at).toLocaleDateString()}</p><h2>{row.label ?? 'Unlabelled claim'}</h2>{#if row.country_code || row.locality}<p>{row.country_code ? countryName(row.country_code) : 'Country not supplied'}{#if row.locality} · {row.locality}{/if}</p>{/if}{#if row.claimed_activity}<p>Claimed activity: {row.claimed_activity}</p>{/if}{#if row.observed_on}<p>Observed on: {row.observed_on}</p>{/if}{#if row.target_record_id}<p>Target record: <code>{row.target_record_id}</code></p>{/if}{#if row.duplicate_record_id}<p>Possible duplicate record: <code>{row.duplicate_record_id}</code></p>{/if}{#if row.location_text}<p>Contributor location text: {row.location_text}</p>{/if}{#if row.claimed_precision}<p>Location detail: {row.claimed_precision}</p>{/if}{#if row.location_input_method}<p>Location entered using: {row.location_input_method === 'manual_pin' ? 'map pin' : row.location_input_method === 'text' ? 'typed coordinates or text' : 'other'}</p>{/if}{#if row.description}<p>{row.description}</p>{/if}{#if row.source_url}<p><a href={row.source_url} rel="noreferrer" target="_blank">Open submitted source</a></p>{/if}{#if row.claimed_latitude !== undefined}<p>Suggested location · {row.claimed_latitude}, {row.claimed_longitude} (not verified)</p>{/if}<div class="decision-actions"><button disabled={busy} onclick={() => decide(row,'hold')}>Hold</button><button disabled={busy} onclick={() => decide(row,'screen')}>Privacy screen only</button><button disabled={busy} onclick={() => decide(row,'reject')}>Reject submission</button><button disabled={busy} onclick={() => decide(row,'restrict')}>Restrict submission</button><button disabled={busy} onclick={() => decide(row,'remove')}>Remove submission</button></div>{#if row.status === 'screened' && row.kind !== 'privacy_removal'}<details class="link-community"><summary>Link to an existing community release record</summary><p>Only link a source-record ID that already belongs to a screened community release. This does not change the public profile or approve curated publication.</p><form onsubmit={(event) => linkCommunity(event,row)}><label>Existing source-record ID<input name="community_record_id" maxlength="36" required /></label><label>Community release ID<input name="release_id" maxlength="160" required /></label><button disabled={busy}>Record link</button></form></details>{/if}</article>{:else}<p class="quiet-note">No items are currently in this page.</p>{/each}{/if}{#if queueError}<p role="alert" class="form-error">{queueError}</p>{/if}{#if queueNotice}<p role="status">{queueNotice}</p>{/if}<p class="quiet-note">Disposition reasons use a fixed category. Never copy identifying claim text into a public note.</p></section>
{:else if page === 'claims'}
  <section class="community-page" aria-labelledby="community-title"><p class="eyebrow">Explicit opt-in profile</p><h1 id="community-title">Community claims</h1><p class="review-warning"><strong>Unreviewed community claim — not verified by Until Every Cage.</strong> This profile contains only claims that passed privacy screening. Screening is not factual review or project approval. Its counts are separate from curated totals.</p>{#if !claims}<form class="contribution-form token-form" onsubmit={(event) => { event.preventDefault(); void loadClaims(); }}><label>Release ID (optional)<input bind:value={communityRelease} autocomplete="off" /></label><p class="quiet-note">Leave blank to use the currently promoted community release.</p><button class="primary-action" disabled={busy}>{busy ? 'Loading…' : 'Open community profile'}</button></form>{:else}<p class="eyebrow">{claims.claim_count} community claims · separate profile count</p><p>{claims.warning}</p>{#each claims.claims as item (item.submission_id)}<button class="claim-row" onclick={() => openClaim(item.submission_id,item.release_id)}><strong>{item.kind.replace('_',' ')}</strong><span>Community-submitted · unreviewed · not project-approved</span><span>Open claim →</span></button>{:else}<p class="quiet-note">No eligible community claims in this release.</p>{/each}{/if}{#if communityError}<p role="alert" class="form-error">{communityError}</p>{/if}</section>
{:else}
  <section class="community-page narrow" aria-labelledby="community-title"><p class="eyebrow">Explicit opt-in profile</p><h1 id="community-title">Community claim</h1><p class="review-warning"><strong>Unreviewed community claim — not verified by Until Every Cage.</strong> This claim has not completed factual review and is not project-approved.</p><button class="primary-action" disabled={busy} onclick={() => void loadClaim()}>{busy ? 'Loading…' : 'Load this claim'}</button>{#if claim}<section class="claim-detail"><p class="eyebrow">Community-submitted · {claim.kind.replace('_',' ')}</p><p>Factual review: unreviewed</p><p>Project approval: not approved</p><p>{claim.warning}</p><a href={claim.public_record_url} target="_blank" rel="noreferrer">View released record data (JSON)</a></section>{/if}{#if communityError}<p role="alert" class="form-error">{communityError}</p>{/if}</section>
{/if}

<style>
  .community-page{color:#eee9df;max-width:48rem;margin:0 auto;padding:1.5rem 1rem 2.5rem;font:.9rem/1.5 system-ui,sans-serif}.community-page.narrow{max-width:42rem}.community-page h1{margin:.15rem 0 .75rem;font:500 clamp(1.65rem,4vw,2rem)/1.08 Georgia,serif;letter-spacing:-.025em}.community-page h2{font:600 1.1rem/1.25 Georgia,serif}.community-page a{color:#dfc99a;text-underline-offset:.2em}.eyebrow{margin:0 0 .4rem;color:#b5b8ac;font:600 .68rem/1.4 ui-monospace,monospace;letter-spacing:.09em;text-transform:uppercase}.lede{max-width:45rem;color:#c6c7be;font-size:.9rem}.contribution-form{display:grid;gap:.75rem;margin-top:.75rem;max-width:46rem}.contribution-form label{display:grid;gap:.38rem;color:#e6e2d8;font-size:.9rem}.contribution-form input,.contribution-form select,.contribution-form textarea{width:100%;min-height:2.5rem;padding:.45rem .6rem;border:1px solid #59615c;border-radius:2px;background:#202523;color:#f4f1e9;font:inherit}.contribution-form textarea{resize:vertical}.contribution-form input:focus-visible,.contribution-form select:focus-visible,.contribution-form textarea:focus-visible,.community-page button:focus-visible{outline:3px solid #d49a62;outline-offset:2px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}.location-picker{display:grid;gap:.7rem;margin:0;padding:.65rem 0;border:0;border-top:1px solid #48514b}.location-picker legend{padding:0 .35rem;font:600 .9rem system-ui}.quiet-note{color:#b8b9b0;font-size:.84rem}.contribution-form .primary-action,.primary-action,.button-link{display:inline-flex;align-items:center;justify-content:center;min-height:2.5rem;width:max-content;max-width:100%;padding:.55rem 1rem;border:1px solid #c58a58;border-radius:2px;background:#8f553d;color:#fff;text-decoration:none;font:600 .9rem system-ui;cursor:pointer}.primary-action:disabled{opacity:.62;cursor:wait}.consent{display:grid!important;grid-template-columns:1.2rem 1fr;align-items:start;gap:.65rem!important}.consent input{width:1.1rem;height:1.1rem;min-height:0;margin:.15rem 0;accent-color:#c88b5b}.form-error{padding:.75rem;border-left:3px solid #d27a66;background:#342422;color:#f1d8d2}.receipt,.status-result,.claim-detail{max-width:43rem;margin-top:1.6rem;padding:1.2rem;border:1px solid #616c63;background:#1e2421}.receipt p{color:#d1d0c7}.receipt :global(.copy-value){margin-top:.9rem}.button-link{margin-top:.4rem}.review-warning{max-width:50rem;margin:1.2rem 0;padding:1rem;border-left:3px solid #cf9a66;background:#282723;color:#eee4ce}.token-form{max-width:37rem}.queue-heading{display:flex;justify-content:space-between;align-items:center;gap:1rem;margin:1.2rem 0}.queue-heading button,.decision-actions button{min-height:2.4rem;padding:.45rem .7rem;border:1px solid #626a64;background:#222725;color:#eee9df;font:inherit;cursor:pointer}.link-community{margin-top:1rem;padding:.75rem 0;border-top:1px solid #4b544d}.link-community summary{cursor:pointer}.link-community p{color:#c0c1b9;font-size:.84rem}.link-community form{display:grid;grid-template-columns:1fr 1fr;gap:.7rem;align-items:end}.link-community label{display:grid;gap:.3rem;color:#ddd8cc;font-size:.83rem}.link-community input{min-height:2.4rem;max-width:100%;padding:.45rem;border:1px solid #59615c;background:#202523;color:#f4f1e9;font:inherit}.link-community button{min-height:2.4rem;padding:.45rem .7rem;border:1px solid #626a64;background:#222725;color:#eee9df;font:inherit;cursor:pointer}.queue-item{margin:1rem 0;padding:1rem 0;border-top:1px solid #515952}.queue-item h2{margin:.2rem 0}.queue-item p{overflow-wrap:anywhere}.queue-item code{font-size:.78rem}.decision-actions{display:flex;flex-wrap:wrap;gap:.45rem;margin-top:1rem}.decision-actions button:hover,.queue-heading button:hover{background:#343b36}.claim-row{display:grid;width:100%;gap:.25rem;padding:1rem .25rem;border:0;border-top:1px solid #555e58;background:transparent;color:#eee9df;text-align:left;cursor:pointer}.claim-row span{color:#bebfb6;font-size:.82rem}.community-unavailable{max-width:46rem;margin:8vh auto;padding:2rem 1.25rem;border-left:2px solid #9d7553;color:#eee9df;font:1rem/1.5 system-ui,sans-serif}.community-unavailable h1{font:500 clamp(2rem,5vw,2.7rem)/1.1 Georgia,serif}.community-unavailable p{max-width:38rem;color:#c5c6bd}.community-unavailable a{color:#dfc99a}@media(max-width:38rem){.form-grid{grid-template-columns:1fr}.queue-heading{align-items:flex-start;flex-direction:column}.link-community form{grid-template-columns:1fr}.community-page{padding-top:1.3rem}}
.community-page.embedded{max-width:none;margin:0;padding:0}.embedded .lede{margin:.7rem 0}.community-unavailable{margin:1rem 0;padding:.75rem 0;border:0}.community-unavailable h1,.community-unavailable h2{font-size:1.1rem}
.field-help{margin:-.3rem 0 0;color:#b8b9b0;font-size:.8rem}
</style>
