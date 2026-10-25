<script lang="ts">
  import { onMount } from 'svelte';
  let { returnMapHref = '#/map', section = 'overview' }: { returnMapHref?: string; section?: 'overview' | 'sources' | 'help' | 'faq' } = $props();
  const context = $derived(returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : '');
  const route = (path: string) => `#/${path}${context}`;
  let estimated = $state(0);
  onMount(() => {
    const openedAt = Date.now();
    const update = () => { estimated = Math.floor((Date.now() - openedAt) / 1000 * (87_892_277_479 / (366 * 86_400))); };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  });
  $effect(() => {
    const id = section;
    if (id !== 'overview') requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }));
  });
</script>
<svelte:head><title>About · Until Every Cage</title><meta name="description" content="Why Until Every Cage maps animal agriculture, how the evidence is handled, and how to take part." /></svelte:head>
<article class="about-page" aria-label="About Until Every Cage">
  <section id="overview" aria-labelledby="about-title">
    <h1 id="about-title">Until every cage is empty</h1>
    <p class="lead">We are an animal-rights research project. We map the places and systems that use animals so their scale can be investigated and challenged.</p>
    <p>Animals are individuals, not database rows. A map point identifies a place in the evidence, not an animal count or a claim that every facility practices the same activities.</p>
    <div class="estimate" aria-labelledby="estimate-title">
      <h2 id="estimate-title">Estimated animals killed</h2>
      <p class="estimate-number" aria-live="off">{estimated.toLocaleString('en-US')} <span>animals</span></p>
      <p class="estimate-caption">Since this page opened · modeled from 2024 global estimates for selected land-animal meat categories.</p>
      <details class="source-note"><summary>Source and method</summary><p>FAOSTAT reports 87,892,277,479 animals slaughtered across 16 selected global land-animal meat categories in 2024. This counter distributes that annual estimate evenly across the 366-day year, about 2,779 animals per second. The selection excludes aquatic animals, aggregate rows, and categories outside those meat items; FAOSTAT inputs can include reported, estimated, supplemented, or imputed values.</p><p>Source: <a href="https://data.fao.org/catalog/iso/55375b1e-51d0-47db-ac9b-536ac8a1c738" target="_blank" rel="noreferrer">FAOSTAT Livestock primary</a>, 2024; retrieved 15 September 2026. <a href="https://files-faostat.fao.org/production/QCL/QCL_methodology_e.pdf" target="_blank" rel="noreferrer">FAOSTAT methodology</a>. Calculation and scope: <a href="https://github.com/eliperez-dev/UntilEveryCage/blob/eli/v2/docs/story/claim-ledger.md#L22-L23" target="_blank" rel="noreferrer">project claim ledger, C-16 and C-17</a>.</p></details>
    </div>
  </section>
  <section id="sources" aria-labelledby="sources-title">
    <h2 id="sources-title">Sources and methods</h2>
    <p>Records retain their source origin, dates, location precision, and available evidence. Interpretation and connections are labeled separately. Coverage is incomplete: absence from the map does not show that a facility is absent or closed.</p>
    <p>Source origin, factual review, privacy screening, project approval, and publication are separate. Community submissions remain a distinct, opt-in profile and do not change curated totals.</p>
    <p>Facility points, approximate locality references, and records without a publishable point have different precision. We do not guess locations.</p>
    <p>Street maps use OpenStreetMap, satellite imagery uses Esri, and 3D terrain uses <a href="https://mapterhorn.com/attribution" target="_blank" rel="noreferrer">Mapterhorn</a>. Map providers receive your IP address and tile requests, not facility records or search text.</p>
    <p><a href={route('database/api')}>Browse public data and releases</a> · <a href={returnMapHref}>Open the map</a></p>
  </section>
  <section id="help" aria-labelledby="help-title">
    <h2 id="help-title">Explore and contribute</h2>
    <p>Search the map or <a href={route('database')}>browse the database</a>, then open a record to inspect its source, dates, precision, and connections.</p>
    <p><a href={route('contribute')}>Contribute</a> to suggest a facility or evidence. Use a correction for an error, duplicate for repeated records, or privacy/removal for a location or personal-information concern. Submissions enter private review and do not automatically change published data. Keep the private tracking link provided after sending.</p>
    <p>For a website issue, use the <a href={route('contribute/bug')}>bug report</a> form.</p>
  </section>
  <section id="faq" aria-labelledby="faq-title">
    <h2 id="faq-title">Common questions</h2>
    <h3>Why is a facility missing?</h3><p>Coverage depends on available sources and is incomplete. Missing records do not establish that a facility does not exist or has closed.</p>
    <h3>How accurate are locations?</h3><p>Check the record’s precision label. Locality references are approximate; some records have no publishable point.</p>
    <h3>Can I reuse the data?</h3><p>See <a href={route('database/api')}>data access and reuse terms</a>. Source and map-provider terms may differ from the project’s compilation license.</p>
  </section>
  <footer><p>Code is available under AGPLv3 or later. <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">Contribute code on GitHub</a> · <a href="mailto:untileverycageproject@protonmail.com">Contact the project</a></p><p class="closing">Until every cage is empty.</p></footer>
</article>
<style>
  .about-page{width:min(100% - 3rem,48rem);margin:auto;padding:1.5rem 0 2.5rem;color:#f1efe8;font:.9rem/1.55 system-ui,sans-serif}
  section{scroll-margin-top:1rem;margin:0 0 1.6rem}h1{margin:0 0 .75rem;font:500 2rem/1.2 Georgia,serif;letter-spacing:-.02em}h2{margin:0 0 .55rem;font:600 1.12rem/1.35 system-ui,sans-serif}h3{margin:1rem 0 .25rem;font:600 .95rem/1.4 system-ui,sans-serif}p{margin:0 0 .7rem;color:#c6d0c5}.lead{font-size:1rem;color:#eee9df}.estimate{margin-top:1.2rem;padding:1rem 1.1rem;border:1px solid #465148;background:#191e1b}.estimate h2{font-size:1rem}.estimate-number{margin:.25rem 0;color:#f0eee7;font:500 clamp(1.4rem,4vw,2rem)/1.2 Georgia,serif;font-variant-numeric:tabular-nums}.estimate-number span{font:.8rem system-ui,sans-serif;color:#c6d0c5}.estimate-caption,.source-note{font-size:.77rem;line-height:1.45}.source-note summary{cursor:pointer;color:#dce8d9;text-underline-offset:.2em}.source-note p{margin:.55rem 0 0}.about-page a{color:#dce8d9;text-underline-offset:.2em;overflow-wrap:anywhere}.about-page footer{border-top:1px solid #3d4740;padding-top:.8rem}.closing{font:italic 1rem Georgia,serif;color:#eee4ce}
  @media(max-width:40rem){.about-page{width:calc(100% - 2rem);padding-top:1.2rem}h1{font-size:1.7rem}.estimate{padding:.8rem}}
</style>
