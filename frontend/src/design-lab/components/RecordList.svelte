<script lang="ts">import type { LabRecord } from '../contract'; let { records, selectedId, onselect, hidden = false }: {records:readonly LabRecord[]; selectedId:string|null; onselect(id:string):void; hidden?:boolean}=$props(); const precisionLabel=(record:LabRecord)=>record.sourceId==='us.fsis'&&record.coordinatePrecision==='source-provided'?'Source-provided coordinate · precision unverified · private rehearsal, not approved':record.precision==='city'?'Approximate city location · not a facility point':record.precision==='exact'?'Numeric source coordinate':record.precision==='approximate'&&record.coordinatePrecision==='source-precision-unknown'?'Approximate source coordinate · precision unknown':record.precision==='approximate'?'Approximate source coordinate':record.precision==='coarse'?'City or postal · no approved map geometry':record.precision==='unmapped'?'Unmapped · list only':`${record.precision} location`;</script>
<section class="record-list" id="record-list" hidden={hidden} aria-labelledby="results-heading"><h2 id="results-heading">Records <span>{records.length}</span></h2>
  {#if records.length > 0}<ol>{#each records as record (record.id)}<li><button data-record-id={record.id} class:active={record.id===selectedId} onclick={() => onselect(record.id)}><strong>{record.name}</strong><small>{record.sourceId ? `${record.sourceId} · ` : ''}{record.locality}, {record.country} · {precisionLabel(record)}</small></button></li>{/each}</ol>{/if}
</section>
<style>
  .record-list h2 { margin:0; padding:.45rem .65rem; border-bottom:1px solid #343a36; font:650 .68rem system-ui; }
  .record-list h2 span { color:#aab0aa; font-weight:500; }
  .record-list ol { margin:0; padding:0; list-style:none; }
  .record-list button { width:100%; padding:.45rem .65rem; border:0; border-bottom:1px solid #303632; background:#171a18; color:#f1efe8; text-align:left; cursor:pointer; }
  .record-list button:hover, .record-list button.active { background:#222723; }
  .record-list button:focus-visible { outline:2px solid #eee7d6; outline-offset:-2px; }
  .record-list strong, .record-list small { display:block; }
  .record-list strong { font:650 .72rem/1.25 system-ui; }
  .record-list small { margin-top:.12rem; color:#aab0aa; font:500 .61rem/1.35 system-ui; }
</style>
