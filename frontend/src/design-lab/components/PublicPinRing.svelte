<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { language, tr } from '../../app/language';
  import { categoryPresentation, CATEGORY_PIN_COLORS, CATEGORY_PRIMARY_BY_SOURCE_KEY } from '../../features/locations/categoryPresentation';
  import type { PinHoverLabel, PinHoverResolver } from '../contract';
  import { recordNamePresentation } from '../../features/locations/recordNamePresentation';
  import { coordinateKey, createConcentricRingLayout, projectRingPoint, ringViewport, type OverlapMember, type RingBounds, type ScreenPoint } from './publicPinOverlap';

  let { members, anchor, anchors, bounds, optimized = false, pinScale = .8, coordinateRadius = 6.5, selectedId, resolveLabel, onreveal, onselect, onclose }:
    { members: readonly OverlapMember[]; anchor: ScreenPoint; anchors: ReadonlyMap<string, ScreenPoint>; bounds: RingBounds;
      optimized?: boolean; pinScale?: number; coordinateRadius?: number; selectedId?: string | null; resolveLabel?: PinHoverResolver | undefined;
      onreveal?: (() => void) | undefined; onselect(member: OverlapMember): void; onclose(): void } = $props();
  const openingBounds = untrack(() => bounds);
  let ready = $state(false);
  let opening = $state(true);
  let progress = $state(0);
  let region = $state<HTMLElement>();
  let focusedIndex = 0;
  let labels = $state<Record<string, PinHoverLabel>>({});
  let hovered = $state<{ id: string; point: ScreenPoint } | null>(null);
  const tooltip = $derived(!opening && hovered && labels[hovered.id] ? { ...labels[hovered.id]!, ...hovered } : null);
  const labelQueue: OverlapMember[] = [];
  const queuedLabels = new Set<string>();
  const labelRequests = new Set<AbortController>();
  let destroyed = false;
  let quietFocus = false;
  const logical = $derived(createConcentricRingLayout(members.length));
  const viewport = $derived(ringViewport(openingBounds, anchor, logical.radius));
  const available = $derived(ringViewport(bounds, anchor, logical.radius));
  const shown = $derived(logical.positions.map(position => ({ ...position, point: projectRingPoint(position, viewport.center) })));
  const artScale = $derived(Math.max(.3, Math.min(40 / 41, pinScale)));
  const covered = $derived(shown.some(entry => entry.point.x - 22 < bounds.left || entry.point.x + 22 > bounds.right
    || entry.point.y - 22 - (optimized ? 0 : 41 * artScale / 2) < bounds.top
    || entry.point.y + 22 - (optimized ? 0 : 41 * artScale / 2) > bounds.bottom));
  const listMode = $derived(viewport.overflow || covered);
  const surface = $derived(listMode ? available : viewport);
  const samePoint = $derived(members.every(member => coordinateKey(member.coordinates) === coordinateKey(members[0]!.coordinates)));
  const title = $derived(tr(samePoint ? 'Records at this map point' : 'Overlapping records', $language));
  const dotSize = $derived(Math.max(4, Math.min(32, coordinateRadius * 2)));
  const fallbackWidth = $derived(Math.max(44, Math.min(304, bounds.right - bounds.left)));
  const fallbackPosition = $derived({ x: Math.max(bounds.left + fallbackWidth / 2, Math.min(bounds.right - fallbackWidth / 2, anchor.x)), y: Math.max(bounds.top + 24, Math.min(bounds.bottom - 24, anchor.y)) });
  let previousMode: string | undefined;
  $effect(() => {
    const mode = !available.usable ? 'compact' : listMode ? 'list' : 'rings';
    untrack(() => {
      clearLabel();
      if (previousMode !== undefined && mode !== previousMode) {
        void tick().then(() => {
          if (document.activeElement !== document.body && !region?.contains(document.activeElement)) return;
          if (mode !== 'compact') void focusMember(focusedIndex);
          else region?.querySelector<HTMLButtonElement>('.ring-reveal, .ring-close')?.focus({ preventScroll: true });
        });
      }
      previousMode = mode;
    });
  });
  function clearLabel() { hovered = null; }
  function warmLabel(member: OverlapMember) {
    if (destroyed || !resolveLabel || labels[member.id] || queuedLabels.has(member.id)) return;
    queuedLabels.add(member.id); labelQueue.push(member); drainLabels();
  }
  function drainLabels() {
    while (!destroyed && labelRequests.size < 3 && labelQueue.length) {
      const member = labelQueue.shift()!;
      const controller = new AbortController(); labelRequests.add(controller);
      let result: PinHoverLabel | null | Promise<PinHoverLabel | null>;
      try { result = resolveLabel?.(member.id, controller.signal) ?? null; }
      catch { result = null; }
      Promise.resolve(result).then(label => {
        if (!destroyed && !controller.signal.aborted && label) labels[member.id] = label;
      }).catch(() => {}).finally(() => { labelRequests.delete(controller); queuedLabels.delete(member.id); drainLabels(); });
    }
  }
  function category(member: OverlapMember) {
    const props = member.feature.properties;
    const keys = Array.isArray(props.category_keys) ? props.category_keys : [props.category_key];
    return ['slaughter', 'research_and_animal_use', 'processing_and_preparation', 'animal_keeping_and_production', 'other_regulated_premises']
      .find(key => keys.some(value => typeof value === 'string' && (CATEGORY_PRIMARY_BY_SOURCE_KEY[value] ?? value) === key))
      ?? CATEGORY_PRIMARY_BY_SOURCE_KEY[String(props.category_key)] ?? 'unclassified';
  }
  function showLabel(member: OverlapMember, point: ScreenPoint, index: number) {
    if (quietFocus) return;
    focusedIndex = index; hovered = { id: member.id, point }; warmLabel(member);
  }
  async function focusMember(index: number, quiet = false) {
    const member = members[index];
    if (!member || !available.usable) return;
    clearLabel(); focusedIndex = index;
    await tick();
    const button = region?.querySelector<HTMLButtonElement>(`[data-record-id="${member.id}"]`);
    quietFocus = quiet; button?.focus({ preventScroll: true }); quietFocus = false;
    const list = button?.closest<HTMLElement>('.ring-list');
    if (list && button) {
      const item = button.getBoundingClientRect(), frame = list.getBoundingClientRect();
      if (item.top < frame.top + 4) list.scrollTop += item.top - frame.top - 4;
      else if (item.bottom > frame.bottom - 4) list.scrollTop += item.bottom - frame.bottom + 4;
    }
  }
  function memberKeyboard(event: KeyboardEvent) {
    if (!['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    const member = (event.target as Element).closest<HTMLElement>('[data-record-index]');
    const index = member ? Number(member.dataset.recordIndex) : focusedIndex;
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? members.length - 1
      : (index + (event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 1) + members.length) % members.length;
    void focusMember(next);
  }
  function isolateList(node: HTMLElement) {
    const stop = (event: Event) => event.stopPropagation();
    const events = ['wheel', 'pointerdown', 'pointermove', 'pointerup', 'touchstart', 'touchmove'];
    for (const name of events) node.addEventListener(name, stop);
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) {
        const member = members[Number((entry.target as HTMLElement).dataset.recordIndex)];
        if (member) warmLabel(member);
      }
    }, { root: node });
    node.querySelectorAll('[data-record-index]').forEach(button => observer.observe(button));
    return { destroy() { observer.disconnect(); for (const name of events) node.removeEventListener(name, stop); } };
  }
  function ringKeyboard(node: HTMLElement) {
    node.addEventListener('keydown', memberKeyboard);
    return { destroy() { node.removeEventListener('keydown', memberKeyboard); } };
  }
  function displayPoint(member: OverlapMember, point: ScreenPoint) {
    const start = anchors.get(member.id) ?? anchor;
    return { x: start.x + (point.x - start.x) * progress, y: start.y + (point.y - start.y) * progress };
  }
  onMount(() => {
    let frame: number | undefined;
    ready = true;
    if (listMode || matchMedia('(prefers-reduced-motion: reduce)').matches) { progress = 1; opening = false; }
    else {
      let start: number | undefined;
      const animate = (now: number) => {
        start ??= now;
        const time = Math.min(1, (now - start) / 180);
        progress = 1 - (1 - time) ** 3;
        if (time < 1) frame = requestAnimationFrame(animate);
        else { opening = false; frame = undefined; }
      };
      frame = requestAnimationFrame(animate);
    }
    if (!listMode) for (const member of members) warmLabel(member);
    if (available.usable) void focusMember(0, true);
    else region?.querySelector<HTMLButtonElement>('.ring-reveal, .ring-close')?.focus({ preventScroll: true });
    return () => { if (frame !== undefined) cancelAnimationFrame(frame); destroyed = true; labelQueue.length = 0; for (const request of labelRequests) request.abort(); clearLabel(); };
  });
</script>

{#if available.usable}
<section class="public-pin-ring" class:ready class:opening bind:this={region} aria-label={title}
  style:--ring-pin-width={`${25 * artScale}px`} style:--ring-pin-height={`${41 * artScale}px`} style:--ring-dot-size={`${dotSize}px`}>
  {#if !listMode}
  <svg class="ring-connections" aria-hidden="true">
    {#each shown as entry (members[entry.index]!.id)}
      {@const member = members[entry.index]!}
      {@const start = anchors.get(member.id) ?? anchor}
      {@const point = displayPoint(member, entry.point)}
      <line class:emphasis={selectedId === member.id || tooltip?.id === member.id} x1={start.x} y1={start.y} x2={point.x} y2={point.y} />
    {/each}
    <circle cx={anchor.x} cy={anchor.y} r="3" />
  </svg>
  {/if}
  <div class="ring-heading" style:left={`${surface.center.x}px`} style:top={`${surface.bounds.top - 26}px`} style:width={`${surface.width}px`}>
    <span>{members.length.toLocaleString()}</span><span class="ring-title" title={title}>{title}</span>
    <button class="ring-close" type="button" aria-label={tr('Close overlapping records', $language)} onclick={onclose}>×</button>
  </div>
  {#if listMode}
  <div class="ring-list" role="group" aria-label={title} tabindex="-1"
    style:left={`${surface.bounds.left}px`} style:top={`${surface.bounds.top}px`} style:width={`${surface.width}px`} style:height={`${surface.height}px`} use:isolateList use:ringKeyboard>
    {#each members as member, index (member.id)}
      {@const categoryKey = labels[member.id]?.categoryKey ?? category(member)}
      <button type="button" class="ring-member ring-list-member" class:selected={selectedId === member.id} data-record-id={member.id} data-record-index={index}
        aria-label={`${labels[member.id] ? recordNamePresentation(labels[member.id]!, label => tr(label, $language)) : `${tr('Record', $language)} ${index + 1}`}, ${tr(categoryPresentation(categoryKey).label, $language)}`}
        aria-pressed={selectedId === member.id} onfocus={() => showLabel(member, anchor, index)} onmouseenter={() => showLabel(member, anchor, index)} onmouseleave={clearLabel}
        onclick={() => { clearLabel(); onselect(member); }}>
        <span class="ring-list-icon" style:--member-color={categoryPresentation(categoryKey).color}>
          {#if optimized}<span class="ring-dot"></span>{:else}<img alt="" draggable="false" src={`${import.meta.env.BASE_URL}v1-pins/marker-icon-2x-${CATEGORY_PIN_COLORS[categoryKey as keyof typeof CATEGORY_PIN_COLORS] ?? 'grey'}.png`} />{/if}
        </span>
        <span><strong class:pending={!labels[member.id]}>{labels[member.id] ? recordNamePresentation(labels[member.id]!, label => tr(label, $language)) : ''}</strong><span>{tr(categoryPresentation(categoryKey).label, $language)}</span></span>
      </button>
    {/each}
  </div>
  {:else}
  <div class="ring-viewport" role="group" aria-label={title} tabindex="-1"
    style:left={`${viewport.bounds.left}px`} style:top={`${viewport.bounds.top}px`} style:width={`${viewport.width}px`} style:height={`${viewport.height}px`} use:ringKeyboard>
    <svg class="ring-guides" aria-hidden="true">
      {#each logical.ringRadii as radius}<circle cx={viewport.width / 2} cy={viewport.height / 2} r={radius} />{/each}
    </svg>
    {#each shown as entry (members[entry.index]!.id)}
      {@const member = members[entry.index]!}
      {@const point = displayPoint(member, entry.point)}
      {@const categoryKey = category(member)}
      <button type="button" class="ring-member" class:selected={selectedId === member.id} class:optimized data-record-id={member.id} data-record-index={entry.index}
        style:left={`${point.x - viewport.bounds.left}px`} style:top={`${point.y - viewport.bounds.top}px`}
        style:--member-color={categoryPresentation(categoryKey).color}
        aria-label={`${labels[member.id] ? recordNamePresentation(labels[member.id]!, label => tr(label, $language)) : `${tr('Record', $language)} ${entry.index + 1}`}, ${tr(categoryPresentation(categoryKey).label, $language)}`}
        aria-pressed={selectedId === member.id}
        onmouseenter={() => showLabel(member, entry.point, entry.index)} onmouseleave={clearLabel}
        onfocus={() => showLabel(member, entry.point, entry.index)} onblur={clearLabel}
        onclick={() => { clearLabel(); onselect(member); }}>
        {#if optimized}<span class="ring-dot"></span>{:else}<img alt="" draggable="false" src={`${import.meta.env.BASE_URL}v1-pins/marker-icon-2x-${CATEGORY_PIN_COLORS[categoryKey as keyof typeof CATEGORY_PIN_COLORS] ?? 'grey'}.png`} />{/if}
      </button>
    {/each}
    {#if tooltip}
      <div class="ring-tooltip" role="tooltip" style:left={`${Math.max(Math.min(112, viewport.width / 2), Math.min(viewport.width - Math.min(112, viewport.width / 2), tooltip.point.x - viewport.bounds.left))}px`}
        style:top={`${Math.max(8, Math.min(viewport.height - 112, tooltip.point.y - viewport.bounds.top - 106))}px`}>
        <strong>{recordNamePresentation(tooltip, label => tr(label, $language))}</strong><span>{tr(categoryPresentation(tooltip.categoryKey).label, $language)}</span>
      </div>
    {/if}
  </div>
  {/if}
</section>
{:else}
<section class="public-pin-ring compact" bind:this={region} aria-label={title}>
  <div class="ring-fallback" style:left={`${fallbackPosition.x}px`} style:top={`${fallbackPosition.y}px`} style:width={`${fallbackWidth}px`}>
    {#if onreveal}<button class="ring-reveal" type="button" onclick={onreveal} aria-label={`${members.length.toLocaleString()} ${tr('Open overlapping records', $language)}`}>
      <strong>{members.length.toLocaleString()}</strong><span>{tr('Open overlapping records', $language)}</span><span aria-hidden="true">↗</span>
    </button>{:else}<span class="ring-fallback-title">{members.length.toLocaleString()} {title}</span>{/if}
    <button class="ring-close" type="button" aria-label={tr('Close overlapping records', $language)} onclick={onclose}>×</button>
  </div>
</section>
{/if}

<style>
  .public-pin-ring{position:absolute;inset:0;z-index:5;pointer-events:none;color:var(--ink,#f2f0e8);font-family:inherit;-webkit-user-select:none;user-select:none}
  .ring-connections{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}
  line{stroke:#4b544d;stroke-width:1;stroke-opacity:.2}line.emphasis{stroke-opacity:.74;stroke-width:1.3}
  circle{fill:#f2f0e8;stroke:#404840;stroke-width:1.5}
  .ring-heading{box-sizing:border-box;position:absolute;transform:translate(-50%,-50%);display:flex;gap:7px;align-items:center;max-width:min(320px,calc(100% - 24px));white-space:nowrap;background:var(--panel,#1c1c1c);color:var(--ink,#f2f0e8);border:1px solid var(--line,#414141);border-radius:4px;padding:1px 3px 1px 12px;font-size:11px;box-shadow:0 3px 10px #0002;pointer-events:auto}
  .ring-heading>span:first-child{font-weight:700;font-variant-numeric:tabular-nums}.ring-title{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}
  button{font:inherit;cursor:pointer;touch-action:manipulation}.ring-close{flex:0 0 44px;width:44px;height:44px;border:0;background:transparent;color:inherit;font-size:20px}
  .ring-viewport{position:absolute;box-sizing:border-box;overflow:hidden;pointer-events:none;border:0;border-radius:4px}
  .ring-guides{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}.ring-guides circle{fill:none;stroke:#4b544d;stroke-width:1;stroke-opacity:.2}
  .ring-member{position:absolute;transform:translate(-50%,-50%);display:grid;place-items:center;width:44px;height:44px;padding:0;border:0;border-radius:50%;background:transparent;pointer-events:auto;opacity:0}
  .ring-member:not(.optimized):not(.ring-list-member){transform:translate(-50%,calc(-50% - var(--ring-pin-height)/2))}
  .ready .ring-member{opacity:1}.ring-member img{width:var(--ring-pin-width);height:var(--ring-pin-height);object-fit:contain;filter:drop-shadow(2px 4px 2px #0005);pointer-events:none}
  .ring-member.selected img,.ring-member:hover img,.ring-member:focus-visible img{filter:drop-shadow(0 0 4px #fff) drop-shadow(1px 4px 3px #0006)}
  .ring-dot{display:block;box-sizing:border-box;width:var(--ring-dot-size);height:var(--ring-dot-size);background:var(--member-color);border:2px solid #172019;border-radius:50%;box-shadow:0 2px 5px #0003}
  .ring-member.selected .ring-dot,.ring-member:hover .ring-dot,.ring-member:focus-visible .ring-dot{outline:3px solid #fff;box-shadow:0 0 8px #fff}
  button:focus-visible,.ring-viewport:focus-visible,.ring-list:focus-visible{outline:2px solid #f2f0e8;outline-offset:2px;box-shadow:0 0 0 4px #30372f}
  .ring-list{position:absolute;box-sizing:border-box;overflow:auto;overscroll-behavior:contain;touch-action:pan-y;pointer-events:auto;background:var(--panel,#1c1c1c);border:1px solid var(--line,#414141);border-radius:4px;padding:4px}
  .ring-list-member{position:static;transform:none;display:flex;align-items:center;gap:9px;width:100%;height:auto;min-height:56px;padding:5px 8px;border:0;border-bottom:1px solid var(--line,#414141);border-radius:0;background:transparent;color:inherit;text-align:left;opacity:1}
  .ring-list-member:last-child{border-bottom:0}.ring-list-member:hover,.ring-list-member.selected{background:var(--panel-raised,#303030)}
  .ring-list-member>span:last-child{min-width:0;flex:1}.ring-list-member strong{display:block;font-size:12px;font-weight:600;overflow-wrap:anywhere;line-height:1.4}.ring-list-member>span:last-child>span{display:block;font-size:11px;opacity:.8;line-height:1.4;margin-top:2px}
  .ring-list-member strong.pending{height:12px;width:65%;margin:3px 0;background:var(--line,#414141);border-radius:2px}
  .ring-list-icon{flex:0 0 28px;display:grid;place-items:center}
  .ring-tooltip{position:absolute;transform:translateX(-50%);box-sizing:border-box;max-width:calc(100% - 16px);width:224px;max-height:104px;overflow:hidden;background:var(--panel,#1c1c1c);color:var(--ink,#f2f0e8);padding:8px 11px;border:1px solid var(--line,#414141);border-radius:6px;box-shadow:0 4px 14px #0002;font-size:12px;line-height:1.4;z-index:7;pointer-events:none}
  .ring-tooltip strong{display:-webkit-box;-webkit-line-clamp:3;line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere;font-weight:600}.ring-tooltip span{display:block;font-size:11px;margin-top:3px;opacity:.8}
  .ring-fallback{position:absolute;transform:translate(-50%,-50%);display:flex;min-height:48px;max-width:calc(100% - 24px);background:var(--panel,#1c1c1c);color:var(--ink,#f2f0e8);border:1px solid var(--line,#414141);border-radius:4px;box-shadow:0 4px 12px #0002;pointer-events:auto}
  .ring-reveal{display:flex;align-items:center;gap:8px;flex:1;min-width:0;min-height:44px;padding:2px 10px;border:0;background:transparent;color:inherit;text-align:left;font-size:12px}
  .ring-reveal strong{font-variant-numeric:tabular-nums}.ring-reveal>span:first-of-type{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ring-fallback>.ring-close{align-self:center}.ring-fallback-title{flex:1;align-self:center;padding:4px 10px;font-size:12px}
</style>
