<script lang="ts">
  import { onMount } from 'svelte';
  import { ANIMAL_KILL_COUNTER_MODEL, ANIMAL_KILL_GROUPS, estimateGroupSinceOpen } from '../features/counter/animalKillCounterModel';

  let elapsedMilliseconds = $state(0);
  onMount(() => {
    const openedAt = performance.now();
    let timer: number | undefined;
    let reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => { elapsedMilliseconds = Math.max(0, performance.now() - openedAt); };
    const stop = () => { if (timer !== undefined) window.clearInterval(timer); timer = undefined; };
    const start = () => {
      stop(); update();
      if (!document.hidden) timer = window.setInterval(update, reducedMotion.matches ? 1000 : 1000 / 30);
    };
    const onVisibility = () => document.hidden ? stop() : start();
    start();
    document.addEventListener('visibilitychange', onVisibility);
    reducedMotion.addEventListener('change', start);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
      reducedMotion.removeEventListener('change', start);
    };
  });
</script>

<section class="estimate" aria-labelledby="estimate-title">
  <h2 id="estimate-title">Estimated animals killed</h2>
  <p class="estimate-caption">Estimated since you opened this page.</p>
  <ul class="estimate-list">
    {#each ANIMAL_KILL_GROUPS as group (group.id)}
      <li><span class="estimate-number">{estimateGroupSinceOpen(group.annualEstimate, elapsedMilliseconds).toLocaleString('en-US')}</span><span>{group.label}</span></li>
    {/each}
  </ul>
  <details class="source-note">
    <summary>Source and method</summary>
    <p>These are modeled estimates carried forward from the V1 counter, not live events or counts at mapped facilities. Each inherited annual rate is spread evenly over a 365-day year. The source detail recorded by V1 is broad, and an edition or year is not retained for some rates; this is not a complete or measured global total.</p>
    <ul>{#each ANIMAL_KILL_GROUPS as group (group.id)}<li>{group.label}: {group.source}</li>{/each}</ul>
    <p>Counter adapted from <a href="https://adaptt.org/" target="_blank" rel="noreferrer">ADAPTT</a>. {ANIMAL_KILL_COUNTER_MODEL.limitation}</p>
  </details>
</section>

<style>
  .estimate{margin-top:1.2rem;padding:1rem 1.1rem;border:1px solid #465148;background:#191e1b}.estimate h2{margin:0 0 .35rem;font:600 1rem/1.35 system-ui,sans-serif;color:#f1efe8}.estimate-caption,.source-note{font: .77rem/1.45 system-ui,sans-serif;color:#c6d0c5}.estimate-caption{margin:0 0 .6rem}.estimate-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.2rem .85rem;margin:0;padding:0;list-style:none}.estimate-list li{display:flex;justify-content:space-between;gap:.65rem;padding:.16rem 0;border-bottom:1px solid #303832}.estimate-number{font-variant-numeric:tabular-nums;color:#f0eee7}.source-note{margin-top:.65rem}.source-note summary{cursor:pointer;color:#dce8d9;text-underline-offset:.2em}.source-note p{margin:.5rem 0}.source-note ul{columns:2;padding-left:1.2rem}.source-note li{break-inside:avoid;margin:.15rem 0}.estimate a{color:#dce8d9}@media(max-width:34rem){.estimate{padding:.8rem}.estimate-list{grid-template-columns:1fr}.source-note ul{columns:1}}
</style>
