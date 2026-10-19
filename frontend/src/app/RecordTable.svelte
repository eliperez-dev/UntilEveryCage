<script lang="ts">
  export type TableRecord = { id: string; name: string; activity: string; place: string; source: string };
  let { records, selectedId = null, onselect }: { records: readonly TableRecord[]; selectedId?: string | null; onselect(id: string): void } = $props();
  type Column = 'name' | 'activity' | 'place' | 'source';
  let widths = $state<Record<Column, number>>({ name: 270, activity: 180, place: 170, source: 180 });
  const minWidth: Record<Column, number> = { name: 180, activity: 130, place: 130, source: 130 };
  function setWidth(column: Column, next: number) {
    widths = { ...widths, [column]: Math.max(minWidth[column], Math.min(520, Math.round(next))) };
  }
  function resizeByKey(event: KeyboardEvent, column: Column) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    setWidth(column, widths[column] + (event.key === 'ArrowRight' ? 24 : -24));
  }
  function beginResize(event: PointerEvent, column: Column) {
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const startWidth = widths[column];
    const move = (pointer: PointerEvent) => setWidth(column, startWidth + pointer.clientX - startX);
    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop, { once: true });
  }
</script>
<table aria-label="Browse records"><colgroup><col style={`width:${widths.name}px`} /><col style={`width:${widths.activity}px`} /><col style={`width:${widths.place}px`} /><col style={`width:${widths.source}px`} /></colgroup><thead><tr>{#each [['name', 'Name'], ['activity', 'Activity'], ['place', 'Place'], ['source', 'Source']] as [column, label]}<th scope="col"><span>{label}</span><button class="column-resize" type="button" aria-label={`Resize ${label} column with left and right arrow keys`} onpointerdown={event => beginResize(event, column as Column)} onkeydown={event => resizeByKey(event, column as Column)}>↔</button></th>{/each}</tr></thead><tbody>{#each records as record (record.id)}<tr class:selected={record.id === selectedId}><td data-label="Name"><button type="button" aria-pressed={record.id === selectedId} onclick={() => onselect(record.id)}>{record.name}</button></td><td data-label="Activity">{record.activity}</td><td data-label="Place">{record.place}</td><td data-label="Source">{record.source}</td></tr>{/each}</tbody></table>
<style>
  table{width:100%;table-layout:fixed;border-collapse:collapse;color:#c8d0c6;font:.82rem/1.35 system-ui,sans-serif}th,td{padding:.42rem .55rem;text-align:left;vertical-align:top;border-bottom:1px solid #3c4640;overflow-wrap:anywhere}th{color:#eef0e8;font-weight:600;font-size:.74rem}th>span{vertical-align:middle}button{padding:0;min-height:1.45rem;background:none;border:0;color:#f1efe8;text-decoration:underline;text-underline-offset:.2em;text-align:left;cursor:pointer;font:600 .84rem/1.3 system-ui,sans-serif}.column-resize{float:right;min-width:1.5rem;min-height:1.5rem;color:#b9c7b8;font-size:.7rem;text-decoration:none;cursor:ew-resize;touch-action:none}tr.selected{background:#1e2a21}tr:hover{background:#18221c}button:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:55rem){thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}colgroup{display:none}tbody{display:block}tr{display:grid;grid-template-columns:1fr 1fr;padding:.25rem;border-bottom:1px solid #3c4640}td{display:block;width:auto;border:0;padding:.25rem;min-width:0}td:first-child{grid-column:1/-1}td::before{content:attr(data-label);display:block;color:#aab8aa;font-size:.7rem;margin-bottom:.05rem}}
</style>
