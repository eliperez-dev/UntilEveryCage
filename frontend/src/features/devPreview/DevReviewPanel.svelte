<script lang="ts">
  import type { DevCandidate } from '../../api/DevCandidatePreviewRepository';
  import { nextLocalReviewState, type LocalReviewState } from './devReviewState';
  export let candidate: DevCandidate | undefined;
  let state: LocalReviewState = 'unreviewed';
  $: if (!candidate) state = 'unreviewed';
</script>

<section class="review-panel" aria-labelledby="private-review-heading">
  <p class="eyebrow">PRIVATE REVIEW NOTES</p>
  <h2 id="private-review-heading">Restricted inspection only</h2>
  <p>This browser-session note does not approve, publish, suppress, or alter the candidate. No secure review write endpoint is available.</p>
  {#if candidate}
    <dl><div><dt>Candidate status</dt><dd>{candidate.releaseStatus} · {candidate.previewLabel}</dd></div><div><dt>Privacy</dt><dd>{candidate.evidence?.privacyScreeningStatus ?? 'unavailable'}</dd></div><div><dt>Coordinates</dt><dd>{candidate.lat === null ? 'Not available for display' : `${candidate.evidence?.displayPrecision ?? 'unknown'} display point`}</dd></div><div><dt>Provenance</dt><dd><a href={candidate.evidence?.sourceUrl} target="_blank" rel="noopener noreferrer">{candidate.source}</a> · retrieved {candidate.evidence?.retrievedAt ?? 'unavailable'}</dd></div><div><dt>Project approval</dt><dd>{candidate.evidence?.projectApproval === false ? 'false — not approved' : 'unavailable'}</dd></div><div><dt>Published profile</dt><dd>{candidate.evidence?.publicationProfile === null ? 'null — not published' : 'unavailable'}</dd></div></dl>
    <p role="status">Session note: {state === 'unreviewed' ? 'not inspected' : state === 'inspected' ? 'inspected locally; no decision recorded' : 'follow-up flagged locally; maintainer action required'}</p>
    <button onclick={() => state = nextLocalReviewState(state, 'inspect')}>Mark inspected in this session</button>
    <button onclick={() => state = nextLocalReviewState(state, 'follow_up')}>Flag maintainer follow-up</button>
  {:else}<p>No candidate selected. Load an authenticated private preview first.</p>{/if}
</section>

<style>.review-panel{border:1px solid #cfc4b2;background:#f3eee6;padding:18px;margin:22px 0}.review-panel h2{margin:0 0 8px}.review-panel p{max-width:760px;line-height:1.5}.review-panel dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.review-panel dt{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:#62594e}.review-panel dd{margin:4px 0 0;overflow-wrap:anywhere}.review-panel a{color:#a34927}.review-panel button{margin:12px 12px 0 0;background:#a34927;color:#fff;border:0;padding:10px 12px;border-radius:3px;font-weight:700}@media(max-width:680px){.review-panel dl{grid-template-columns:1fr}}</style>
