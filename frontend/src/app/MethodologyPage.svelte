<script lang="ts">
  import PreviewMasthead from './PreviewMasthead.svelte';
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  let databaseHref = $derived(returnMapHref.includes('?') ? `#/database?${returnMapHref.split('?')[1]}` : '#/database');
</script>
<svelte:head><title>Sources & Methodology · Until Every Cage</title><meta name="description" content="Source evidence, location precision, publication, and corrections." /></svelte:head>
<PreviewMasthead current="about" mapHref={returnMapHref} {databaseHref} />
<main id="main-content" class="methodology">
  <h1>Sources & Methodology</h1>
  <p>Coverage depends on the sources and records in the selected release. The map is an evidence index, not a complete census.</p>
  <section aria-labelledby="sources-heading">
    <h2 id="sources-heading">Sources and releases</h2>
    <p>Each record starts with a source observation. Record details show its origin, dates, and available evidence. Project classifications and inferred connections remain separate from original source statements.</p>
    <p>Factual review, privacy screening, project approval, and publication are separate decisions. Community submissions stay outside curated totals and carry their own review labels.</p>
  </section>
  <section aria-labelledby="precision-heading">
    <h2 id="precision-heading">Location precision</h2>
    <dl>
      <div><dt>Facility point</dt><dd>A published coordinate associated with a record; its source and precision still matter.</dd></div>
      <div><dt>Locality reference</dt><dd>A centroid is not a facility point. City, commune, municipality, or postal references are approximate; map halos are visual aids, not measured boundaries.</dd></div>
      <div><dt>Without a point</dt><dd>Records without publishable coordinates remain searchable. We do not guess a location.</dd></div>
    </dl>
    <p>Maps use OpenStreetMap tiles; viewing a map contacts the tile provider. Placing a pin supplies the chosen location directly.</p>
  </section>
  <section aria-labelledby="limits-heading">
    <h2 id="limits-heading">Limits</h2>
    <p>Sources differ in scope, age, and quality. Inclusion does not establish current operation, an exact operating address, ownership, supply-chain activity, or wrongdoing. Absence does not prove that no facility exists.</p>
    <p>Source-supported and inferred connections are labeled separately. An inference is a lead for investigation, not proof of identity or ownership.</p>
  </section>
  <section aria-labelledby="corrections-heading">
    <h2 id="corrections-heading">Corrections & privacy</h2>
    <p>For incorrect records, residential locations, or personal exposure, email <a href="mailto:untileverycageproject@protonmail.com">untileverycageproject@protonmail.com</a> with the record link and concern. Use “Privacy/location removal” for a location-exposure concern.</p>
    <a href={databaseHref}>Explore the Database</a>
  </section>
</main>
<style>
  .methodology{width:min(100% - 3rem,46rem);margin:auto;padding:1.5rem 0 2.5rem;color:#f1efe8;font:.9rem/1.5 system-ui,sans-serif;min-height:calc(100dvh - 4rem)}
  h1{margin:0 0 1rem;font:500 2rem/1.15 Georgia,serif;letter-spacing:-.02em}h2{margin:0 0 .5rem;font:600 1.1rem/1.3 system-ui,sans-serif}section{margin-top:1.5rem}p{margin:0 0 .75rem;color:#c6d0c5}a{color:#dce8d9;text-underline-offset:.2em;overflow-wrap:anywhere}dl{margin:0 0 .75rem}dl div{display:grid;grid-template-columns:9rem minmax(0,1fr);gap:1rem;margin:.6rem 0}dt{font-weight:600}dd{margin:0;color:#c6d0c5}
  @media(max-width:40rem){.methodology{width:calc(100% - 2rem)}h1{font-size:1.65rem}dl div{grid-template-columns:1fr;gap:.2rem}}
</style>
