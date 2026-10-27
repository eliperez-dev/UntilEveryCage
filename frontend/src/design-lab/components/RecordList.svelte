<script lang="ts">
  import CategoryBadge from '../../features/locations/CategoryBadge.svelte';
  import { classificationSummary } from '../../features/locations/classificationSummary';
  import { language, tr } from '../../app/language';
  import type { LabRecord } from '../contract';
  let { records, selectedId, onselect, hidden = false }: {records:readonly LabRecord[]; selectedId:string|null; onselect(id:string):void; hidden?:boolean}=$props();
  const rows = $derived(records.map(record => ({ record, summary: classificationSummary(record, label => tr(label, $language)).summary })));
  const precisionLabel=(record:LabRecord)=>record.sourceId==='us.fsis'&&record.coordinatePrecision==='source-provided'?'Source-provided coordinate · precision unverified · private rehearsal, not approved':record.precision==='city'?'Approximate city location · not a facility point':record.precision==='exact'?'Numeric source coordinate':record.precision==='approximate'&&record.coordinatePrecision==='source-precision-unknown'?'Approximate source coordinate · precision unknown':record.precision==='approximate'?'Approximate source coordinate':record.precision==='coarse'?'City or postal · no approved map geometry':record.precision==='unmapped'?'Unmapped · list only':record.precision==='source_reported'?'Source-provided coordinates':`${record.precision} location`;
</script>
<section class="record-list" id="record-list" hidden={hidden} aria-labelledby="results-heading"><h2 id="results-heading">{tr('Records', $language)} <span>{records.length}</span></h2>
  {#if rows.length > 0}<ol>{#each rows as { record, summary } (record.id)}<li><button data-record-id={record.id} class:active={record.id===selectedId} onclick={() => onselect(record.id)}><strong>{record.name}</strong><span class="record-category"><CategoryBadge {record} /></span>{#if summary}<span class="activity-summary">{summary}</span>{/if}<small>{[record.locality, record.country].filter(Boolean).join(', ')}{record.locality || record.country ? ' · ' : ''}{tr(precisionLabel(record), $language)}</small>{#if record.sourceName}<small class="source-meta">{record.sourceName}</small>{/if}</button></li>{/each}</ol>{/if}
</section>
<style>
  .record-list h2 { margin:0; padding:.45rem .65rem; border-bottom:1px solid #343a36; font:650 .68rem system-ui; }
  .record-list h2 span { color:#aab0aa; font-weight:500; }
  .record-list ol { margin:0; padding:0; list-style:none; }
  .record-list button { width:100%; min-height:44px; padding:var(--result-row-padding, .45rem) .65rem; border:0; border-bottom:1px solid var(--line,#383838); background:var(--panel,#1c1c1c); color:var(--ink,#f0efeb); text-align:left; cursor:pointer; }
  .record-list button:hover, .record-list button.active { background:var(--panel-hover,#262626); }
  .record-list button:focus-visible { outline:2px solid #eee7d6; outline-offset:-2px; }
  .record-category { display: block; margin: .3rem 0 .1rem; color: inherit; }
  .activity-summary { display:block;margin:.35rem 0;font:400 calc(.8125rem * var(--result-type-scale,1))/1.5 system-ui;overflow-wrap:anywhere; }
  .record-list small.source-meta { margin-top:.2rem; }
  .record-list strong, .record-list small { display:block; }
  .record-list strong { font:650 calc(.72rem * var(--result-type-scale, 1))/1.25 system-ui; }
  .record-list small { margin-top:.12rem; color:#aab0aa; font:500 calc(.61rem * var(--result-type-scale, 1))/1.35 system-ui; }
</style>
