<script lang="ts">
  import { tick, untrack } from 'svelte';
  import { CommunityError, createCommunityRepository, type ContributionDraft, type Receipt, type SubmissionKind } from '../../api/CommunityRepository';
  import { language, tr } from '../language';
  import { countryOptions } from '../countryOptions';
  import { TAXONOMY_PRIMARY_KEYS } from '../../domain/taxonomy';
  import { CATEGORY_PRESENTATIONS } from '../../features/locations/categoryPresentation';
  import ContributionRecordPicker from './ContributionRecordPicker.svelte';
  import { buildIntakePayload, emptyIntakeDraft, intakeTitles, validateIntakeDraft, type IntakeDraft, type IntakeErrors } from './contributionForm';
  let { kind = 'facility', draft = $bindable(emptyIntakeDraft()), targetRecordId = '', returnMapHref = '#/map', onreceived, onbusychange, submitOverride }: { kind?: SubmissionKind; draft?: IntakeDraft; targetRecordId?: string; returnMapHref?: string; onreceived?(receipt: Receipt): void; onbusychange?(busy: boolean): void; submitOverride?(payload: ContributionDraft): Promise<void> } = $props();
  let form: HTMLFormElement;
  let busy = $state(false), submitError = $state('');
  let errors = $state<IntakeErrors>({});
  let PinPicker = $state<typeof import('../ContributionPinPicker.svelte').default | null>(null);
  let pickerError = $state(false);
  const repository = createCommunityRepository();
  const releaseId = $derived(new URLSearchParams(returnMapHref.split('?')[1] ?? '').get('release_id') ?? undefined);
  const coordinateKind = $derived(kind === 'facility' || kind === 'correction');
  const descriptionLabel = $derived(kind === 'correction' ? 'What should be corrected?' : kind === 'privacy_removal' ? 'What should we review?' : kind === 'evidence' ? 'What did you find? (optional if you added a source link)' : kind === 'duplicate' ? 'Why do these records look like duplicates? (optional)' : kind === 'bug' ? 'What happened?' : 'Additional context (optional)');
  $effect(() => { kind; targetRecordId; untrack(() => { errors = {}; submitError = ''; if (targetRecordId && !draft.targetReference) draft.targetReference = targetRecordId; }); });
  $effect(() => { if (draft.locationOpen && coordinateKind && !PinPicker && !pickerError) void loadPicker(); });
  async function loadPicker() {
    pickerError = false;
    try { PinPicker = (await import('../ContributionPinPicker.svelte')).default; }
    catch { pickerError = true; }
  }
  function precisionChanged() { if (draft.precision === 'unmapped') { draft.latitude = undefined; draft.longitude = undefined; draft.locationInputMethod = undefined; } }
  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (busy) return;
    errors = validateIntakeDraft(kind, draft); submitError = '';
    if (errors.latitude || errors.longitude) draft.locationOpen = true;
    if (errors.contactEmail) draft.contactOpen = true;
    if (Object.keys(errors).length) { await tick(); form.querySelector<HTMLElement>('[aria-invalid="true"], summary[data-invalid="true"]')?.focus(); return; }
    const requestKind = kind, requestDraft = draft;
    busy = true; onbusychange?.(true);
    try {
      const payload = buildIntakePayload(requestKind, requestDraft);
      if (submitOverride) await submitOverride(payload);
      else { const receipt = await repository.submit(payload); if (kind === requestKind && draft === requestDraft) onreceived?.(receipt); }
    }
    catch (error) { if (kind === requestKind && draft === requestDraft) submitError = error instanceof CommunityError ? error.message : 'Your contribution could not be sent. Try again.'; }
    finally { busy = false; onbusychange?.(false); }
  }
</script>
<section class="intake" aria-label={tr('Contribution form', $language)}>
  <header><h2>{tr(intakeTitles[kind], $language)}</h2><span>{tr('* Required', $language)}</span></header>
  {#if kind === 'privacy_removal'}<p class="private-note">{tr('Sent privately to the review team.', $language)}</p>{/if}
  <form bind:this={form} onsubmit={submit} novalidate>
    {#if kind !== 'facility' && kind !== 'bug'}<ContributionRecordPicker id="intake-target" label="Facility" bind:value={draft.targetReference} error={errors.targetReference ?? ''} {releaseId} />{/if}
    {#if kind === 'duplicate'}<ContributionRecordPicker id="intake-duplicate" label="Possible duplicate" bind:value={draft.duplicateReference} error={errors.duplicateReference ?? ''} {releaseId} />{/if}
    {#if kind === 'facility'}
      <label>{tr('Facility name', $language)} *<input name="label" bind:value={draft.label} maxlength="160" required aria-invalid={errors.label ? 'true' : undefined} aria-describedby={errors.label ? 'label-error' : undefined} />{#if errors.label}<span class="field-error" id="label-error" role="alert">{tr(errors.label, $language)}</span>{/if}</label>
      <div class="field-row"><label>{tr('Country (optional)', $language)}<select name="country_code" bind:value={draft.countryCode}><option value="">{tr('Unknown / not sure', $language)}</option>{#each countryOptions as country (country.code)}<option value={country.code}>{country.name}</option>{/each}</select></label><label>{tr('Locality (optional)', $language)}<input name="locality" bind:value={draft.locality} maxlength="160" /></label></div>
    {/if}
    {#if kind !== 'bug'}<label>{tr('Source link (optional)', $language)}<input name="source_url" bind:value={draft.sourceUrl} type="url" maxlength="2048" placeholder="https://…" aria-invalid={errors.sourceUrl ? 'true' : undefined} aria-describedby={errors.sourceUrl ? 'source-error' : undefined} />{#if errors.sourceUrl}<span class="field-error" id="source-error" role="alert">{tr(errors.sourceUrl, $language)}</span>{/if}</label>{/if}
    <label>{tr(descriptionLabel, $language)}{#if ['correction','privacy_removal','bug'].includes(kind)} *{/if}<textarea name="description" bind:value={draft.description} maxlength="2000" rows="3" required={['correction','privacy_removal','bug'].includes(kind)} aria-invalid={errors.description ? 'true' : undefined} aria-describedby={errors.description ? 'description-error' : undefined}></textarea>{#if errors.description}<span class="field-error" id="description-error" role="alert">{tr(errors.description, $language)}</span>{/if}</label>
    {#if kind === 'bug'}
      <label>{tr('Steps to reproduce', $language)} *<textarea name="steps" bind:value={draft.reproductionSteps} required maxlength="2000" rows="3" aria-invalid={errors.reproductionSteps ? 'true' : undefined} aria-describedby={errors.reproductionSteps ? 'steps-error' : undefined}></textarea>{#if errors.reproductionSteps}<span class="field-error" id="steps-error" role="alert">{tr(errors.reproductionSteps, $language)}</span>{/if}</label>
      <label>{tr('Page link (optional)', $language)}<input name="page_url" bind:value={draft.pageUrl} type="url" maxlength="1000" placeholder="https://…" aria-invalid={errors.pageUrl ? 'true' : undefined} />{#if errors.pageUrl}<span class="field-error" role="alert">{tr(errors.pageUrl, $language)}</span>{/if}</label>
    {/if}
    {#if ['facility','evidence','bug'].includes(kind)}<details bind:open={draft.detailsOpen}><summary>{tr('Additional details (optional)', $language)}</summary><div class="details-fields">
      {#if kind === 'facility'}<label>{tr('Primary activity (optional)', $language)}<select name="claimed_activity" bind:value={draft.claimedActivity}><option value="">{tr('Choose a category', $language)}</option>{#each TAXONOMY_PRIMARY_KEYS as category}<option value={category}>{tr(category === 'unclassified' ? 'Other / Unknown (unclassified)' : CATEGORY_PRESENTATIONS[category].label, $language)}</option>{/each}</select></label>{/if}
      {#if kind === 'bug'}<label>{tr('What did you expect?', $language)}<textarea name="expected" bind:value={draft.expectedBehavior} maxlength="1000" rows="2"></textarea></label>{:else}<label>{tr('When did you observe this? (optional)', $language)}<input name="observed_on" bind:value={draft.observedOn} type="date" /></label>{/if}
    </div></details>{/if}
    {#if coordinateKind}<details bind:open={draft.locationOpen}><summary data-invalid={errors.latitude || errors.longitude ? 'true' : undefined} aria-describedby={errors.latitude || errors.longitude ? 'coordinates-error' : undefined}>{tr('Add location details (optional)', $language)}</summary><div class="details-fields">
      <label>{tr('Location note (optional)', $language)}<input name="location_text" bind:value={draft.locationText} maxlength="1000" placeholder={tr('City or broad area', $language)} /></label>
      <p class="field-help">{tr('Leave coordinates blank if you’re unsure.', $language)}</p>
      {#if draft.locationOpen && PinPicker}<PinPicker latitude={draft.latitude} longitude={draft.longitude} onpoint={(latitude, longitude, method) => { draft.latitude = latitude; draft.longitude = longitude; draft.locationInputMethod = method; if (latitude !== undefined && longitude !== undefined && draft.precision === 'unmapped') draft.precision = 'unknown'; }} onclear={() => { draft.latitude = undefined; draft.longitude = undefined; draft.locationInputMethod = undefined; }} />{:else if pickerError}<p class="field-help" role="alert">{tr('The location picker could not be opened.', $language)} <button class="text-action" type="button" onclick={() => void loadPicker()}>{tr('Retry', $language)}</button></p><div class="field-row"><label>{tr('Latitude', $language)}<input type="number" min="-90" max="90" step="any" bind:value={draft.latitude} /></label><label>{tr('Longitude', $language)}<input type="number" min="-180" max="180" step="any" bind:value={draft.longitude} /></label></div>{:else if draft.locationOpen}<p class="field-help" role="status">{tr('Loading location picker…', $language)}</p>{/if}
      {#if errors.latitude || errors.longitude}<p id="coordinates-error" class="field-error" role="alert">{tr(errors.latitude ?? errors.longitude ?? '', $language)}</p>{/if}
      <label>{tr('Location detail', $language)}<select bind:value={draft.precision} onchange={precisionChanged}><option value="unknown">{tr('Not sure', $language)}</option><option value="exact">{tr('Exact point', $language)}</option><option value="coarse">{tr('Around this area', $language)}</option><option value="unmapped">{tr('No point', $language)}</option></select></label>
    </div></details>{/if}
    <details bind:open={draft.contactOpen}><summary>{tr('Add follow-up contact (optional)', $language)}</summary><div class="details-fields"><label>{tr('Email for follow-up (optional)', $language)}<input name="contact_email" bind:value={draft.contactEmail} type="email" maxlength="254" autocomplete="email" aria-invalid={errors.contactEmail ? 'true' : undefined} aria-describedby="contact-help" />{#if errors.contactEmail}<span class="field-error" role="alert">{tr(errors.contactEmail, $language)}</span>{/if}</label><p id="contact-help" class="field-help">{tr('For questions about this contribution.', $language)}</p></div></details>
    {#if kind !== 'bug'}<label class="consent"><input type="checkbox" bind:checked={draft.consent} required aria-invalid={errors.consent ? 'true' : undefined} aria-describedby={errors.consent ? 'consent-error' : undefined} /><span>{tr('I have permission to share this information.', $language)}</span></label>{#if errors.consent}<p class="field-error" id="consent-error" role="alert">{tr(errors.consent, $language)}</p>{/if}{/if}
    {#if submitError}<p class="form-error" role="alert">{tr(submitError, $language)}</p>{/if}
    <div class="form-actions"><span>{tr('No account needed.', $language)}</span><button class="primary-action" type="submit" disabled={busy}>{tr(busy ? 'Sending…' : kind === 'bug' ? 'Send report' : 'Send for review', $language)} <span aria-hidden="true">→</span></button></div>
  </form>
</section>
<style>
  .intake{color:var(--ink);font:.9rem/1.5 system-ui,sans-serif;min-width:0}header{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;margin-bottom:1.4rem}h2{font:400 clamp(1.5rem,3vw,1.8rem)/1.15 Georgia,serif;letter-spacing:-.025em;margin:0}header>span{font-size:.75rem;color:var(--ink-muted);white-space:nowrap}.private-note{color:var(--ink-muted);font-size:.8rem;margin:0 0 1rem}form{display:grid;gap:1rem}label{display:grid;gap:.4rem;color:var(--ink);font-size:.8rem;font-weight:500}input:not([type=checkbox]),select,textarea{width:100%;min-height:2.75rem;padding:.6rem .75rem;color:var(--ink);background:var(--panel);border:1px solid var(--line-strong);border-radius:0;font:400 .9rem/1.5 system-ui,sans-serif}textarea{resize:vertical}input::placeholder{color:var(--ink-muted)}.field-row{display:grid;grid-template-columns:1fr 1fr;gap:1rem;min-width:0}.field-row>label{min-width:0}details{padding-top:.7rem;border-top:1px solid var(--line)}summary{min-height:2.75rem;padding:.4rem 0;cursor:pointer;color:var(--ink-muted);font-size:.8rem}.details-fields{display:grid;gap:1rem;margin:.5rem 0 .25rem}.details-fields :global(.coordinate-inputs input){min-height:2.75rem;background:var(--panel);color:var(--ink);border-color:var(--line-strong);border-radius:0}.details-fields :global(.coordinate-inputs label){color:var(--ink)}.details-fields :global(.clear-point){min-height:2.75rem;color:var(--ink);background:var(--panel);border-color:var(--line-strong);border-radius:0}.field-help{margin:0;color:var(--ink-muted);font-size:.75rem}.consent{display:flex;align-items:flex-start;gap:.7rem;min-height:2.75rem;padding:.5rem 0;font-weight:400}.consent input{margin:.2rem 0 0;min-height:1rem;width:1rem;height:1rem;accent-color:var(--ink);flex:none}.field-error{font-size:.8rem;margin:0;font-weight:400;color:var(--ink)}[aria-invalid=true]{border-color:var(--focus)!important}.form-error{border-left:2px solid var(--focus);padding:.5rem .75rem;margin:0;color:var(--ink);font-size:.85rem}.form-actions{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding-top:.35rem}.form-actions>span{font-size:.75rem;color:var(--ink-muted)}button{min-height:2.75rem;border-radius:0;font:inherit}.primary-action{padding:.65rem 1rem;background:var(--ink);color:var(--page);border:1px solid var(--ink);cursor:pointer}.primary-action:disabled{opacity:.6;cursor:wait}.text-action{padding:0 .5rem;border:0;background:transparent;color:var(--ink);text-decoration:underline}:is(input,select,textarea,button,summary):focus-visible{outline:3px solid var(--focus);outline-offset:3px}@media(max-width:38rem){.field-row{grid-template-columns:1fr}input:not([type=checkbox]),select,textarea{font-size:1rem}header{gap:.6rem}.form-actions .primary-action{min-width:9rem}}
</style>
