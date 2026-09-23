<script lang="ts">import type { LabRecord } from '../contract'; let { records, selectedId, onselect, hidden = false }: {records:readonly LabRecord[]; selectedId:string|null; onselect(id:string):void; hidden?:boolean}=$props();</script>
<section class="record-list" id="record-list" hidden={hidden} aria-labelledby="results-heading"><h2 id="results-heading">Synchronized records <span>{records.length}</span></h2>
  {#if records.length > 0}<ol>{#each records as record (record.id)}<li><button class:active={record.id===selectedId} onclick={() => onselect(record.id)}><strong>{record.name}</strong><small>{record.locality}, {record.country} · {record.precision}</small></button></li>{/each}</ol>{/if}
</section>
