<script lang="ts">
  import type { LabRecord } from '../design-lab/contract';

  /** Safe fields returned by the local private-preview detail projection. */
  export type RecordDetailRecord = Partial<Omit<LabRecord, 'name' | 'category'>> & {
    id?: string;
    candidateId?: string;
    candidate_id?: string;
    name?: string | null;
    displayName?: string | null;
    display_name?: string | null;
    category?: string | null;
    activityLabel?: string | null;
    activity_label?: string | null;
    activitySource?: string | null;
    activity_source?: string | null;
    sourceId?: string | null;
    source_id?: string | null;
    sourceName?: string | null;
    source_name?: string | null;
    safeSourceRecordId?: string | null;
    sourceRecordId?: string | null;
    source_record_id?: string | null;
    sourceUrl?: string | null;
    source_url?: string | null;
    sourceRecordUrl?: string | null;
    source_record_url?: string | null;
    retrievedAt?: string | null;
    retrieved_at?: string | null;
    observedAt?: string | null;
    observed_at?: string | null;
    evidenceSummary?: string | null;
    evidence_summary?: string | null;
    locality?: string | null;
    country?: string | null;
    precision?: LabRecord['precision'] | null;
    latitude?: number | null;
    longitude?: number | null;
    reviewStatus?: string | null;
    coordinateReviewStatus?: string | null;
    coordinate_review_status?: string | null;
    factualReviewStatus?: string | null;
    factual_review_status?: string | null;
    privacyScreeningStatus?: string | null;
    privacy_screening_status?: string | null;
    publicationStatus?: string | null;
    publication_status?: string | null;
    projectApproval?: string | boolean | null;
    previewLabel?: string | null;
    coordinatePrecision?: string | null;
    displayPrecision?: string | null;
    display_precision?: string | null;
  };

  let {
    record,
    presentation = 'rail',
    onclose,
  }: {
    record: LabRecord | RecordDetailRecord;
    presentation?: 'rail' | 'page';
    onclose?: () => void;
  } = $props();

  let copied = $state(false);

  const value = (...items: Array<string | null | undefined>) =>
    items.find((item) => typeof item === 'string' && item.trim())?.trim() ?? null;

  const id = $derived(
    value(
      record.id,
      'candidateId' in record ? record.candidateId : null,
      'candidate_id' in record ? record.candidate_id : null,
    ) ?? '',
  );
  const name = $derived(
    value(
      'displayName' in record ? record.displayName : null,
      'display_name' in record ? record.display_name : null,
      record.name,
    ) ?? 'Name unavailable',
  );
  const activity = $derived(
    value(
      'activityLabel' in record ? record.activityLabel : null,
      'activity_label' in record ? record.activity_label : null,
      record.category,
    ),
  );
  const sourceId = $derived(
    value(record.sourceId, 'source_id' in record ? record.source_id : null),
  );
  const sourceName = $derived(
    value(
      'sourceName' in record ? record.sourceName : null,
      'source_name' in record ? record.source_name : null,
    ),
  );
  const sourceUrl = $derived(
    safeHttps(
      value(
        'sourceUrl' in record ? record.sourceUrl : null,
        'source_url' in record ? record.source_url : null,
      ),
    ),
  );
  const sourceRecordUrl = $derived(
    safeHttps(
      value(
        'sourceRecordUrl' in record ? record.sourceRecordUrl : null,
        'source_record_url' in record ? record.source_record_url : null,
      ),
    ),
  );
  const precision = $derived(
    value(
      record.precision,
      'displayPrecision' in record ? record.displayPrecision : null,
      'display_precision' in record ? record.display_precision : null,
    ) ?? 'unmapped',
  );
  const coordinateStatus = $derived(
    value(
      record.reviewStatus,
      'coordinateReviewStatus' in record ? record.coordinateReviewStatus : null,
      'coordinate_review_status' in record ? record.coordinate_review_status : null,
    ),
  );
  const factualStatus = $derived(
    value(
      'factualReviewStatus' in record ? record.factualReviewStatus : null,
      'factual_review_status' in record ? record.factual_review_status : null,
    ),
  );
  const privacyStatus = $derived(
    value(
      'privacyScreeningStatus' in record ? record.privacyScreeningStatus : null,
      'privacy_screening_status' in record ? record.privacy_screening_status : null,
    ),
  );
  const publicationStatus = $derived(
    value(
      'publicationStatus' in record ? record.publicationStatus : null,
      'publication_status' in record ? record.publication_status : null,
    ),
  );
  const retrieved = $derived(
    value(
      'retrievedAt' in record ? record.retrievedAt : null,
      'retrieved_at' in record ? record.retrieved_at : null,
    ),
  );
  const observed = $derived(
    value(
      'observedAt' in record ? record.observedAt : null,
      'observed_at' in record ? record.observed_at : null,
    ),
  );
  const evidence = $derived(
    value(
      'evidenceSummary' in record ? record.evidenceSummary : null,
      'evidence_summary' in record ? record.evidence_summary : null,
    ),
  );
  const activitySource = $derived(
    value(
      'activitySource' in record ? record.activitySource : null,
      'activity_source' in record ? record.activity_source : null,
    ),
  );
  const sourceRecordId = $derived(
    value(
      'safeSourceRecordId' in record ? record.safeSourceRecordId : null,
      'sourceRecordId' in record ? record.sourceRecordId : null,
      'source_record_id' in record ? record.source_record_id : null,
    ),
  );
  const previewLabel = $derived(
    value('previewLabel' in record ? record.previewLabel : null) ??
      'Private development preview · not publication-approved',
  );
  const locationText = $derived(
    [value(record.locality), value(record.country)].filter(Boolean).join(', ') ||
      'Location unavailable',
  );
  const precisionLabel = $derived(precisionLabelFor(precision));

  function humanizeValue(raw: string | null): string | null {
    if (!raw) return null;

    // These are display labels only; keep the repository's canonical enum untouched.
    const words = raw.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
    return words ? words[0]!.toLocaleUpperCase() + words.slice(1) : null;
  }

  function safeHttps(raw: string | null): string | null {
    if (!raw) return null;
    try {
      const url = new URL(raw);
      // External evidence links are shown only for encrypted web URLs.
      return url.protocol === 'https:' ? url.href : null;
    } catch { return null; }
  }
  function precisionLabelFor(raw: string): string {
    if (raw === 'exact' || raw.includes('source_numeric')) {
      return 'Source coordinate · review status shown below';
    }
    if (raw === 'city' || raw.includes('city_reference')) {
      return 'City reference · approximate';
    }
    if (raw === 'coarse' || raw.includes('city_postal')) {
      return 'Coarse city/postal area';
    }
    if (raw === 'approximate' || raw.includes('approximate')) {
      return 'Approximate source coordinate';
    }
    return 'Unmapped · no map location supplied';
  }
  async function copyUrl() {
    const url = typeof window === 'undefined'
      ? ''
      : `${window.location.origin}${window.location.pathname}#/records/${encodeURIComponent(id)}`;
    if (!url || !navigator.clipboard?.writeText) return;
    try {
      await navigator.clipboard.writeText(url);
      copied = true;
      window.setTimeout(() => (copied = false), 1800);
    } catch {
      copied = false;
    }
  }
</script>

<article
  class:page={presentation === 'page'}
  class="detail"
  aria-labelledby="record-title"
>
  {#if onclose}
    <button
      class="close"
      type="button"
      aria-label="Close record detail"
      onclick={onclose}
    >Close</button>
  {/if}
  <p class="context">PRIVATE DEVELOPMENT PREVIEW · NOT PUBLICATION-APPROVED</p>
  <p class="kind">Facility candidate</p>
  <h1 id="record-title">{name}</h1>
  {#if activity}
    <p class="activity">
      {activity}{#if activitySource}<span> · {activitySource}</span>{/if}
    </p>
  {/if}
  <p class="place">{locationText}</p>

  <section aria-labelledby="location-heading">
    <h2 id="location-heading">Location</h2>
    <dl>
      <div>
        <dt>Location precision</dt>
        <dd>{precisionLabel}</dd>
      </div>
      {#if 'coordinatePrecision' in record && record.coordinatePrecision}
        <div>
          <dt>Source precision</dt>
          <dd>{humanizeValue(record.coordinatePrecision)}</dd>
        </div>
      {/if}
      {#if coordinateStatus}
        <div>
          <dt>Coordinate review</dt>
          <dd>{humanizeValue(coordinateStatus)}</dd>
        </div>
      {/if}
    </dl>
  </section>

  <section aria-labelledby="evidence-heading">
    <h2 id="evidence-heading">Source and review</h2>
    <dl>
      {#if sourceName}
        <div>
          <dt>Source</dt>
          <dd>
            {#if sourceUrl}
              <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                {sourceName}<span class="sr-only"> (opens in a new tab)</span>
              </a>
            {:else}
              {sourceName}
            {/if}
          </dd>
        </div>
      {:else if sourceId}
        <div>
          <dt>Source ID</dt>
          <dd>{sourceId}</dd>
        </div>
      {/if}
      {#if sourceRecordId}
        <div>
          <dt>Source record</dt>
          <dd>{sourceRecordId}</dd>
        </div>
      {/if}
      {#if sourceRecordUrl}
        <div>
          <dt>Source record link</dt>
          <dd>
            <a href={sourceRecordUrl} target="_blank" rel="noopener noreferrer">
              Open source record<span class="sr-only"> (opens in a new tab)</span>
            </a>
          </dd>
        </div>
      {/if}
      {#if retrieved}
        <div>
          <dt>Retrieved</dt>
          <dd><time datetime={retrieved}>{retrieved}</time></dd>
        </div>
      {/if}
      {#if observed}
        <div>
          <dt>Observed</dt>
          <dd><time datetime={observed}>{observed}</time></dd>
        </div>
      {/if}
      {#if factualStatus}
        <div>
          <dt>Factual review</dt>
          <dd>{humanizeValue(factualStatus)}</dd>
        </div>
      {/if}
      {#if privacyStatus}
        <div>
          <dt>Privacy screening</dt>
          <dd>{humanizeValue(privacyStatus)}</dd>
        </div>
      {/if}
      {#if 'projectApproval' in record && record.projectApproval !== undefined && record.projectApproval !== null}
        <div>
          <dt>Project approval</dt>
          <dd>{humanizeValue(String(record.projectApproval))}</dd>
        </div>
      {/if}
      {#if publicationStatus}
        <div>
          <dt>Publication</dt>
          <dd>{humanizeValue(publicationStatus)}</dd>
        </div>
      {/if}
    </dl>
    {#if evidence}<p class="evidence">{evidence}</p>{/if}
  </section>

  <section aria-labelledby="limitations-heading">
    <h2 id="limitations-heading">Limitations</h2>
    <p>{previewLabel}</p>
    <p>Source origin does not establish accuracy, current operation, project approval, or publication.</p>
  </section>

  <footer>
    <span class="record-id">Record ID · {id || 'Unavailable'}</span>
    <button
      type="button"
      onclick={copyUrl}
      disabled={!id}
      aria-label="Copy stable record URL"
    >{copied ? 'Copied' : 'Copy record link'}</button>
  </footer>
</article>

<style>
  .detail {
    --ink: #f1efe8;
    --muted: #aab0aa;
    --line: #414843;
    box-sizing: border-box;
    min-width: 0;
    /* The host rail owns scrolling so the detail panel does not create a nested scroll region. */
    overflow: visible;
    padding: 1.1rem;
    color: var(--ink);
    background: #171a18;
    font: 0.82rem/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  }

  .detail * {
    box-sizing: border-box;
  }

  .context {
    margin: 0;
    color: #c8d0c5;
    font: 0.6rem/1.4 ui-monospace, monospace;
    letter-spacing: 0.08em;
  }

  .kind {
    margin: 1.2rem 0 0.2rem;
    color: var(--muted);
    font-size: 0.72rem;
  }

  .detail h1 {
    margin: 0.25rem 2rem 0.3rem 0;
    font: 500 1.55rem/1.2 Georgia, serif;
  }

  .activity,
  .place {
    margin: 0.25rem 0;
    color: #d5d9d3;
  }

  .activity span,
  .place {
    color: var(--muted);
  }

  section {
    margin-top: 1.2rem;
  }

  h2 {
    margin: 0;
    padding: 0.55rem 0;
    border-bottom: 1px solid var(--line);
    font: 600 0.9rem/1.3 system-ui, sans-serif;
  }

  dl {
    margin: 0.2rem 0;
  }

  dl div {
    display: grid;
    grid-template-columns: minmax(7rem, 34%) 1fr;
    gap: 0.7rem;
    padding: 0.55rem 0;
    border-bottom: 1px solid #303632;
  }

  dt {
    color: var(--muted);
    font-size: 0.72rem;
  }

  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }

  a {
    color: #ddd4bb;
    text-underline-offset: 2px;
  }

  .evidence,
  section > p {
    color: #c2c8c1;
    font-size: 0.75rem;
  }

  footer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    margin-top: 1.1rem;
    padding-top: 0.8rem;
    border-top: 1px solid var(--line);
  }

  .record-id {
    overflow-wrap: anywhere;
    color: var(--muted);
    font: 0.65rem ui-monospace, monospace;
  }

  button {
    min-height: 2.5rem;
    padding: 0.45rem 0.7rem;
    border: 1px solid #69716a;
    color: var(--ink);
    background: #202421;
    font: inherit;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .close {
    float: right;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  .page {
    min-height: 100%;
    max-width: 58rem;
    margin: auto;
    padding: clamp(1.2rem, 5vw, 3rem);
  }

  .page h1 {
    font-size: clamp(1.8rem, 4vw, 2.5rem);
  }

  @media (max-width: 40rem) {
    .detail {
      border-top: 1px solid var(--line);
      padding: 1rem;
    }

    .page {
      min-height: 100dvh;
    }

    .page footer {
      position: sticky;
      bottom: 0;
      background: #171a18;
    }
  }
</style>
