<script lang="ts">
  import { onMount } from 'svelte';
  import { language, tr } from '../../app/language';
  import { categoryPresentation, CATEGORY_PRIMARY_BY_SOURCE_KEY } from '../../features/locations/categoryPresentation';
  import { recordNamePresentation } from '../../features/locations/recordNamePresentation';
  import type { PublicPinSummary, PublicPinSummaryResolver } from '../contract';
  import { coordinateKey, overlapPanelFrame, type OverlapBounds, type OverlapMember, type ScreenPoint } from './publicPinOverlap';

  let { members, anchor, bounds, resolveLabel, onselect, onclose }: {
    members: readonly OverlapMember[];
    anchor: ScreenPoint;
    bounds: OverlapBounds;
    resolveLabel?: PublicPinSummaryResolver | undefined;
    onselect(member: OverlapMember): void;
    onclose(): void;
  } = $props();

  const frame = $derived(overlapPanelFrame(bounds, anchor, members.length));
  const samePoint = $derived(members.every(member => coordinateKey(member.coordinates) === coordinateKey(members[0]!.coordinates)));
  const title = $derived(tr(samePoint ? 'Records at this map point' : 'Overlapping records', $language));
  let list: HTMLUListElement;
  let labels = $state<Record<string, PublicPinSummary | null>>({});
  const queue: OverlapMember[] = [];
  const requestedIds = new Set<string>();
  const activeRequests = new Set<AbortController>();
  let destroyed = false;

  function loadLabel(member: OverlapMember) {
    if (!resolveLabel || requestedIds.has(member.id)) return;
    requestedIds.add(member.id);
    queue.push(member);
    drainLabels();
  }

  function drainLabels() {
    while (!destroyed && activeRequests.size < 3 && queue.length) {
      const member = queue.shift()!;
      const request = new AbortController();
      activeRequests.add(request);
      void Promise.resolve()
        .then(() => resolveLabel?.(member.id, request.signal))
        .then(label => { if (!request.signal.aborted) labels[member.id] = label ?? null; })
        .catch(() => { if (!request.signal.aborted) labels[member.id] = null; })
        .finally(() => { activeRequests.delete(request); drainLabels(); });
    }
  }

  function category(member: OverlapMember) {
    const props = member.feature.properties;
    const keys = Array.isArray(props.category_keys) ? props.category_keys : [props.category_key];
    return ['slaughter', 'research_and_animal_use', 'processing_and_preparation', 'animal_keeping_and_production', 'other_regulated_premises']
      .find(key => keys.some(value => typeof value === 'string' && (CATEGORY_PRIMARY_BY_SOURCE_KEY[value] ?? value) === key))
      ?? CATEGORY_PRIMARY_BY_SOURCE_KEY[String(props.category_key)] ?? 'unclassified';
  }

  function focusMember(index: number) {
    const button = list.querySelector<HTMLButtonElement>(`[data-record-index="${index}"]`);
    if (!button) return;
    button.focus({ preventScroll: true });
    const item = button.getBoundingClientRect();
    const visible = list.getBoundingClientRect();
    if (item.top < visible.top) list.scrollTop += item.top - visible.top;
    else if (item.bottom > visible.bottom) list.scrollTop += item.bottom - visible.bottom;
  }

  function onNavigation(event: KeyboardEvent, index: number) {
    const direction = { ArrowRight: 1, ArrowLeft: -1, ArrowUp: -1, ArrowDown: 1 }[event.key];
    if (event.key !== 'Home' && event.key !== 'End' && !direction) return;
    event.preventDefault();
    event.stopPropagation();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? members.length - 1
      : (index + direction! + members.length) % members.length;
    focusMember(next);
  }

  onMount(() => {
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const member = members[Number((entry.target as HTMLElement).dataset.recordIndex)];
        if (member) loadLabel(member);
      }
    }, { root: list });
    list.querySelectorAll('[data-record-index]').forEach(button => observer.observe(button));
    focusMember(0);
    return () => {
      destroyed = true;
      observer.disconnect();
      for (const request of activeRequests) request.abort();
    };
  });
</script>

<section class="public-overlap-panel" id="public-overlap-panel" aria-labelledby="public-overlap-title"
  style:--overlap-left={`${frame.left}px`} style:--overlap-top={`${frame.top}px`}
  style:--overlap-width={`${frame.width}px`} style:--overlap-height={`${frame.maxHeight}px`} style:--map-toolbar-bottom={`${bounds.top}px`}>
  <header>
    <h2 id="public-overlap-title">{members.length.toLocaleString($language)} {title}</h2>
    <button class="close" type="button" aria-label={tr('Close overlapping records', $language)} onclick={onclose}>×</button>
  </header>
  <ul bind:this={list}>
    {#each members as member, index (member.id)}
      {@const label = labels[member.id]}
      {@const appearance = categoryPresentation(label?.categoryKey ?? category(member))}
      <li>
        <button type="button" class="overlap-member" data-record-id={member.id} data-record-index={index}
          onfocus={() => loadLabel(member)} onkeydown={event => onNavigation(event, index)} onclick={() => onselect(member)}>
          <span class="activity-dot" style:background={appearance.color} aria-hidden="true"></span>
          <span class="member-text">
            {#if label}
              <strong>{recordNamePresentation(label, text => tr(text, $language))}</strong>
            {:else if label === undefined && resolveLabel}
              <span class="pending-name" aria-hidden="true"></span>
              <span class="visually-hidden">{tr('Loading record…', $language)}</span>
            {:else}
              <strong>{tr('Record', $language)} {index + 1}</strong>
            {/if}
            <small>{tr(appearance.label, $language)}</small>
          </span>
          <span class="chevron" aria-hidden="true">›</span>
        </button>
      </li>
    {/each}
  </ul>
</section>

<style>
  .public-overlap-panel {
    position: absolute;
    z-index: 5;
    top: var(--overlap-top);
    left: var(--overlap-left);
    display: flex;
    flex-direction: column;
    width: var(--overlap-width);
    max-height: var(--overlap-height);
    overflow: hidden;
    border: 1px solid #ddd6c8;
    border-radius: .375rem;
    background: #faf8f1;
    color: #262421;
    color-scheme: light;
    box-shadow: 0 5px 18px #0003;
  }
  header { display: flex; align-items: center; justify-content: space-between; gap: .25rem; padding: .2rem .25rem .2rem .8rem; border-bottom: 1px solid #e0d9cd; }
  h2 { margin: 0; font-size: .95rem; line-height: 1.3; font-weight: 650; }
  button { border: 0; color: inherit; background: transparent; font: inherit; cursor: pointer; touch-action: manipulation; }
  button:focus-visible { outline: 2px solid #8d413d; outline-offset: -3px; }
  .close { flex: 0 0 44px; height: 44px; padding: 0; font-size: 1.25rem; line-height: 1; }
  ul { min-height: 0; margin: 0; padding: 0; overflow-y: auto; overscroll-behavior: contain; touch-action: pan-y; list-style: none; }
  li + li { border-top: 1px solid #e7e0d4; }
  .overlap-member { display: grid; grid-template-columns: 8px minmax(0, 1fr) min-content; align-items: center; gap: .65rem; width: 100%; min-height: 48px; padding: .4rem .8rem; text-align: left; }
  .close:hover, .overlap-member:hover { background: #eee8dc; }
  .activity-dot { width: 7px; height: 7px; border-radius: 50%; }
  .member-text { overflow-wrap: anywhere; }
  .member-text strong { display: block; font-size: .875rem; line-height: 1.25; font-weight: 600; }
  .pending-name { display: block; width: 62%; height: .65rem; margin: .22rem 0; border-radius: .2rem; background: #e7e0d4; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  small { display: block; margin-top: .1rem; color: #5e5952; font-size: .75rem; line-height: 1.25; }
  .chevron { color: #5e5952; }
  @media (max-width: 40rem) {
    .public-overlap-panel {
      inset: auto 0 0;
      width: 100%;
      max-height: min(44dvh, calc(100% - var(--map-toolbar-bottom, 0px)));
      padding-bottom: env(safe-area-inset-bottom, 0px);
      border-radius: .65rem .65rem 0 0;
    }
  }
</style>
