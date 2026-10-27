<script lang="ts">
  import { onDestroy } from 'svelte';
  import { language, tr } from '../../app/language';
  import { sheetHeights, nearestSheetSnap, sheetKeyboardSnap, type SheetSnap } from './mobileSheet';
  let { open, snap, detail = false, preview = false, available, middlePercent = 48, expandedPercent = 90, onchange, onheight }: {
    open: boolean; detail?: boolean; preview?: boolean; available: number; middlePercent?: number; expandedPercent?: number;
    snap: SheetSnap; onchange(next: SheetSnap): void; onheight(height: number): void;
  } = $props();
  let safeArea = $state(0);
  let handle: HTMLButtonElement;
  let drag = $state<{ id: number; startY: number; startHeight: number; moved: boolean; startSnap: SheetSnap } | null>(null);
  let dragHeight = $state<number | null>(null);
  let ignoredClick = false;
  let frame = 0;
  let lastHeight = 56;
  const heights = $derived(sheetHeights(available, { middlePercent, expandedPercent }, safeArea));
  const current = $derived<SheetSnap>(open ? snap : 'collapsed');
  $effect(() => {
    lastHeight = dragHeight ?? heights[current];
    onheight(lastHeight);
  });
  function measure(node: HTMLButtonElement) {
    const update = () => { safeArea = parseFloat(getComputedStyle(node).getPropertyValue('--sheet-safe-bottom')) || 0; };
    update(); window.addEventListener('resize', update);
    return { destroy() { window.removeEventListener('resize', update); } };
  }
  function focusHandle() { handle?.focus({ preventScroll: true }); }
  function choose(next: SheetSnap) {
    if (next === 'collapsed') focusHandle();
    onchange(next);
  }
  function click() {
    if (ignoredClick) { ignoredClick = false; return; }
    choose(current === 'collapsed' ? 'middle' : current === 'middle' ? 'expanded' : 'collapsed');
  }
  function keydown(event: KeyboardEvent) {
    const next = sheetKeyboardSnap(event.key, current);
    if (next) { event.preventDefault(); choose(next); }
  }
  function pointerdown(event: PointerEvent) {
    if (event.button !== 0) return;
    event.stopPropagation();
    ignoredClick = false;
    drag = { id: event.pointerId, startY: event.clientY, startHeight: lastHeight, moved: false, startSnap: current };
    handle.setPointerCapture(event.pointerId);
  }
  function pointermove(event: PointerEvent) {
    if (!drag || event.pointerId !== drag.id) return;
    const delta = drag.startY - event.clientY;
    if (Math.abs(delta) < 6 && !drag.moved) return;
    drag.moved = true;
    const height = Math.max(heights.collapsed, Math.min(heights.expanded, drag.startHeight + delta));
    if (!open) { dragHeight = height; onchange('middle'); }
    if (frame) cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => { frame = 0; dragHeight = height; });
  }
  function finish(event: PointerEvent, cancelled = false) {
    if (!drag || drag.id !== event.pointerId) return;
    event.stopPropagation();
    const ended = drag;
    if (frame) { cancelAnimationFrame(frame); frame = 0; }
    drag = null;
    dragHeight = null;
    if (cancelled && handle.hasPointerCapture(ended.id)) handle.releasePointerCapture(ended.id);
    if (ended.moved) {
      ignoredClick = true;
      if (!cancelled) choose(nearestSheetSnap(ended.startHeight + ended.startY - event.clientY, heights));
      else onchange(ended.startSnap);
    }
  }
  onDestroy(() => { if (frame) cancelAnimationFrame(frame); if (drag && handle?.hasPointerCapture(drag.id)) handle.releasePointerCapture(drag.id); });
</script>

<button bind:this={handle} use:measure class="mobile-sheet-handle" class:collapsed={!open} class:dragging={Boolean(drag?.moved)} type="button"
  aria-label={tr(preview ? 'View facility details' : 'Search map', $language)} aria-expanded={open} aria-controls={detail ? 'field-detail-content' : 'field-search-content'}
  data-sheet-state={current} onclick={click} onkeydown={keydown} onpointerdown={pointerdown} onpointermove={pointermove}
  onpointerup={event => finish(event)} onpointercancel={event => finish(event, true)} onlostpointercapture={event => finish(event, true)}>
  <span class="grip" aria-hidden="true"></span><span class="handle-label">{tr(preview ? 'View facility details' : 'Search map', $language)}</span>
  <svg viewBox="0 0 24 24" aria-hidden="true"><path d={current === 'expanded' ? 'm6 9 6 6 6-6' : 'm6 15 6-6 6 6'} /></svg>
</button>

<style>
  .mobile-sheet-handle { display:none; }
  @media(max-width:40rem) {
    .mobile-sheet-handle { --sheet-safe-bottom:env(safe-area-inset-bottom);position:relative;display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:.75rem;width:100%;height:calc(56px + env(safe-area-inset-bottom));min-height:56px;padding:12px 1rem max(0px,env(safe-area-inset-bottom));border:0;background:var(--panel);color:var(--ink);font:500 .8125rem/1.3 system-ui,sans-serif;touch-action:none;cursor:ns-resize;user-select:none; }
    .grip { position:absolute;top:7px;left:calc(50% - 18px);height:3px;width:36px;background:var(--muted);opacity:.65;border-radius:2px; }
    svg { width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.6; }
    .mobile-sheet-handle:not(.collapsed) { height:44px;min-height:44px;padding-top:10px;padding-bottom:0;font-size:.75rem;color:var(--muted); }
    .mobile-sheet-handle:focus-visible { outline:2px solid var(--focus,var(--ink));outline-offset:-3px; }
    .dragging { cursor:grabbing; }
  }
</style>
