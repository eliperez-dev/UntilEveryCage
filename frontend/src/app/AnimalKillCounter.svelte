<script lang="ts">
  import { onMount } from 'svelte';
  import { ANIMAL_KILL_GROUPS, estimateGroupSinceOpen } from '../features/counter/animalKillCounterModel';

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
  <h2 id="estimate-title">Animals Killed Since You Opened This Page</h2>
  <ul class="estimate-list">
    {#each ANIMAL_KILL_GROUPS as group (group.id)}
      <li><span class="estimate-number">{estimateGroupSinceOpen(group.annualEstimate, elapsedMilliseconds).toLocaleString('en-US')}</span><span>{group.label}</span></li>
    {/each}
  </ul>
</section>

<style>
  .estimate{margin-top:1.2rem;padding:1rem 1.1rem;border:1px solid #465148;background:#191e1b}.estimate h2{margin:0 0 .35rem;font:600 1rem/1.35 system-ui,sans-serif;color:#f1efe8}.estimate-list{display:grid;grid-template-columns:1fr;gap:.2rem;margin:0;padding:0;list-style:none}.estimate-list li{display:flex;justify-content:space-between;gap:.65rem;padding:.16rem 0;border-bottom:1px solid #303832}.estimate-number{font-variant-numeric:tabular-nums;color:#f0eee7}@media(max-width:34rem){.estimate{padding:.8rem}}
</style>
