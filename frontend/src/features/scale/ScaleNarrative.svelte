<script lang="ts">
  import { scaleSteps, formatCount } from './scaleModel';

  let selectedIndex = 0;
  $: selected = scaleSteps[selectedIndex] ?? scaleSteps[0];
</script>

<!-- Dev/private narrative prototype: no sourced aggregate or production claim is embedded here. -->
<section class="scale-story" aria-labelledby="scale-heading">
  <div class="story-copy">
    <p class="eyebrow">A SCALE CHECK · SYNTHETIC MODEL</p>
    <h2 id="scale-heading">Start with one individual.</h2>
    <p class="lead">A record can point to a place. It cannot turn the lives represented by a count into anonymous dots.</p>
    <p>This small interaction is a model for making scale easier to hold in mind. It is not a biography, a live counter, or a measured total.</p>
  </div>

  <div class="scale-card">
    <div class="individual-card" role="img" aria-label="A neutral abstract representation of one individual animal. No identity or biography is implied."><span aria-hidden="true">●</span><strong>ONE INDIVIDUAL</strong></div>
    <label for="scale-range">How large is the example?</label>
    <input id="scale-range" type="range" min="0" max={scaleSteps.length - 1} step="1" bind:value={selectedIndex} aria-describedby="scale-note" aria-valuetext={selected.label} />
    <div class="scale-labels" aria-hidden="true">
      {#each scaleSteps as step, index}
        <span class:current={index === selectedIndex}>{step.label}</span>
      {/each}
    </div>
    <div class="estimate" aria-live="polite">
      <span class="eyebrow">MODEL ESTIMATE · SYNTHETIC</span>
      <strong>{formatCount(selected.estimate)}</strong>
      <span>{selected.label}: individuals represented in this bounded example</span>
    </div>
    <p id="scale-note" class="uncertainty"><strong>Uncertainty:</strong> {selected.uncertainty}. Scope: a fictional interaction, not a published facility or geographic total. Date: model authored 2026-09-13.</p>
  </div>

  <div class="method-note">
    <p class="eyebrow">MEASURED VS MODELLED</p>
    <p><strong>Measured</strong> observations belong to a dated source record. <strong>Modelled</strong> values are arithmetic chosen to explain a relationship. This page uses the second kind only.</p>
    <p class="boundary-note"><strong>Synthetic scale example ends here.</strong> The next section contains source-linked facility records.</p>
    <a class="explorer-link" href="#research-heading">Continue to the source-linked explorer ↓</a>
  </div>
</section>

<style>
  .scale-story { display:grid; grid-template-columns:minmax(0,1fr) minmax(280px,.8fr); gap:32px 7vw; padding:42px 0 56px; border-bottom:1px solid #cfc4b2; }
  .story-copy { max-width:560px; }
  .eyebrow { color:#a34927; font-size:.7rem; letter-spacing:.16em; font-weight:800; margin:0 0 14px; }
  h2 { font:600 clamp(2rem,4vw,3.5rem)/1 Georgia,serif; letter-spacing:-.04em; margin:0 0 16px; }
  p { color:#4f5c69; line-height:1.55; }
  .lead { color:#17283b; font-size:1.2rem; }
  .scale-card { background:#f8f4ed; border:1px solid #cfc4b2; padding:24px; align-self:start; }
  .individual-card { display:flex; align-items:center; gap:10px; border-bottom:1px solid #cfc4b2; padding-bottom:16px; margin-bottom:18px; color:#17283b; letter-spacing:.08em; font-size:.78rem; }
  .individual-card span { font-size:1.5rem; line-height:1; color:#a34927; }
  label { display:block; font-weight:800; }
  input { accent-color:#a34927; display:block; margin:26px 0 12px; width:100%; }
  .scale-labels { display:flex; justify-content:space-between; gap:8px; font-size:.72rem; color:#62594e; }
  .scale-labels span { max-width:84px; }
  .scale-labels .current { color:#a34927; font-weight:800; }
  .estimate { border-top:1px solid #cfc4b2; margin-top:24px; padding-top:18px; display:grid; gap:5px; }
  .estimate strong { font:600 clamp(2.2rem,5vw,4rem)/1 Georgia,serif; color:#17283b; }
  .estimate > span:last-child { color:#62594e; }
  .uncertainty { font-size:.82rem; margin-bottom:0; }
  .method-note { grid-column:1 / -1; max-width:720px; border-top:1px solid #cfc4b2; padding-top:20px; }
  .method-note p { margin-top:0; }
  .explorer-link { color:#a34927; font-weight:800; }
  .boundary-note { border-left:3px solid #a34927; padding-left:12px; }
  @media (max-width:680px) { .scale-story { display:block; padding-top:32px; } .scale-card { margin-top:28px; } .method-note { margin-top:30px; } }
  @media (prefers-reduced-motion: reduce) { * { scroll-behavior:auto; } }
</style>
