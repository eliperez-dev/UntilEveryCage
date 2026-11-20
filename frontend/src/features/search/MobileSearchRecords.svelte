<script lang="ts">
  import type { LabRecord } from '../../design-lab/contract';
  import { language,tr } from '../../app/language';
  import { recordNamePresentation } from '../locations/recordNamePresentation';
  import { recordCategoryIdentity } from '../locations/classificationSummary';
  let {records,selectedId,publicRelease=true,onselect}:{records:readonly LabRecord[];selectedId:string|null;publicRelease?:boolean;onselect(id:string):void}=$props();
  const short:Record<string,string>={slaughter:'Slaughter',animal_keeping_and_production:'Animal keeping',processing_and_preparation:'Processing',research_and_animal_use:'Research',other_regulated_premises:'Other premises',unclassified:'Unclassified'};
  function precision(record:LabRecord){return tr(!publicRelease&&record.sourceId==='us.fsis'&&record.coordinatePrecision==='source-provided'?'Source-provided coordinate · precision unverified · private rehearsal, not approved':record.precision==='unmapped'?'Unmapped':record.precision==='city'?'Approximate city location · not a facility point':record.precision==='coarse'?'City or postal · no approved map geometry':record.precision==='source_reported'?'Source-reported':record.precision==='exact'?'Exact':'Approximate',$language);}
</script>
<section class="mobile-record-list" aria-label={tr('Records',$language)}>
  <ol>{#each records as record (record.id)}
    {@const category = recordCategoryIdentity(record)}
    {@const name = recordNamePresentation(record, label => tr(label, $language))}
    {@const location = [...new Set([record.locality, record.country].filter(Boolean))].join(', ')}
    {@const meta = [tr(short[category.key] ?? category.label, $language), location,
      ...(!publicRelease || !['exact','source_reported'].includes(record.precision) ? [precision(record)] : [])].filter(Boolean).join(' · ')}
    <li><button type="button" data-record-id={record.id} class:active={record.id === selectedId} onclick={() => onselect(record.id)}>
      <img src={`${import.meta.env.BASE_URL}v1-pins/${category.pinFile}`} alt="" width="16" height="26" />
      <span class="row-copy"><strong>{name}</strong><span class="record-meta">{meta}</span></span>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7"/></svg>
    </button></li>
  {/each}</ol>
</section>
<style>
  .mobile-record-list{flex:none}ol{list-style:none;margin:0;padding:0}button{display:flex;align-items:flex-start;gap:.6rem;width:100%;min-height:62px;padding:.6rem .8rem;border:0;border-bottom:1px solid var(--line);background:none;color:var(--ink);text-align:left;cursor:pointer;font:inherit}button:hover,button.active{background:var(--panel-hover)}img{width:16px;height:26px;flex:none;object-fit:contain;margin-top:1px}.row-copy{flex:1;min-width:0;display:block}strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:600 .875rem/1.35 var(--ui-font);margin:0 0 .2rem}.record-meta{display:block;color:var(--muted);font-size:.8125rem;line-height:1.35;overflow-wrap:anywhere}svg{width:12px;height:12px;flex:none;fill:none;stroke:var(--muted);stroke-width:1.4;margin-top:3px}button:focus-visible{outline:2px solid var(--ink);outline-offset:-3px}
</style>
