<script lang="ts">
  import type { ContributionDraft } from '../../../api/CommunityRepository';
  import type { VerifiedSecureMessage } from '../../../features/contributions/secureInbox';
  import { CATEGORY_PRESENTATIONS, categoryPresentation } from '../../../features/locations/categoryPresentation';
  import { countryName } from '../../countryOptions';
  import { language, tr } from '../../language';
  import { displaySecureDate } from './secureUi';
  let { messages }: { messages: readonly VerifiedSecureMessage[] } = $props();
  const fields: readonly [keyof ContributionDraft, string][] = [
    ['label','Facility name'],['target_record_id','Linked record'],['duplicate_record_id','Possible duplicate'],['country_code','Country'],['locality','Locality'],['claimed_activity','Activity'],['description','Description'],['source_url','Source link'],['observed_on','Observed on'],['location_text','Location note'],['claimed_latitude','Latitude'],['claimed_longitude','Longitude'],['claimed_precision','Location detail'],['location_input_method','Location entered using'],['expected_behavior','Expected behavior'],['reproduction_steps','Steps to reproduce'],['page_url','Page link'],['contact_email','Follow-up contact'],
  ];
  function display(draft: ContributionDraft, key: keyof ContributionDraft) {
    const value = draft[key];
    if (key === 'country_code' && typeof value === 'string') return countryName(value);
    if (key === 'claimed_activity' && typeof value === 'string') return value in CATEGORY_PRESENTATIONS ? tr(categoryPresentation(value).label, $language) : value;
    if (key === 'location_input_method') return tr(value === 'manual_pin' ? 'Map pin' : value === 'text' ? 'Text' : 'Unknown', $language);
    if (key === 'claimed_precision') return tr(value === 'exact' ? 'Exact point' : value === 'coarse' ? 'Around this area' : value === 'unmapped' ? 'No point' : 'Not sure', $language);
    return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
  }
</script>
<ol class="messages" aria-label={tr('Inbox messages', $language)}>
  {#each messages as message (message.id)}<li><article>
    <header><strong>{tr(message.author === 'reviewer' ? 'Reviewer' : 'Contributor', $language)}</strong><time datetime={message.createdAt}>{displaySecureDate(message.createdAt)}</time></header>
    {#if message.kind === 'submission' && message.draft}<h2>{tr('Submitted information', $language)}</h2><dl>{#each fields as [key,label]}{#if message.draft[key] !== undefined && message.draft[key] !== ''}<div><dt>{tr(label, $language)}</dt><dd>{display(message.draft,key)}</dd></div>{/if}{/each}</dl>
    {:else}<p class="message-body">{message.text ?? ''}</p>{/if}
  </article></li>{/each}
</ol>
<style>
  .messages{list-style:none;margin:0;padding:0;color:var(--ink);font:.85rem/1.5 system-ui,sans-serif;min-width:0}li{border-top:1px solid var(--line);padding:1.1rem 0}header{display:flex;justify-content:space-between;gap:1rem;align-items:baseline;margin-bottom:.8rem}strong{font-weight:500;font-size:.85rem}time{font-size:.75rem;color:var(--ink-muted)}h2{font:400 1.5rem/1.2 Georgia,serif;margin:.4rem 0 1rem}dl{margin:0;display:grid;gap:.9rem}dt{font-size:.75rem;color:var(--ink-muted);margin:0 0 .2rem}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}.message-body{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:38rem){header{flex-wrap:wrap;gap:.35rem}}
</style>
