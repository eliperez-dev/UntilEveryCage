<script lang="ts">
  let { returnMapHref = '#/map', section = 'overview' }: { returnMapHref?: string; section?: 'overview' | 'sources' } = $props();
  const context = $derived(returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : '');
  const route = (path: string) => `#/${path}${context}`;
  $effect(() => {
    const id = section;
    if (id !== 'overview') requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }));
  });
</script>
<svelte:head><title>About · Until Every Cage</title><meta name="description" content="About the project Until Every Cage and its mission." /></svelte:head>
<article class="about-page" aria-label="About Until Every Cage">
  <div class="identity-layout">
    <section id="overview" class="manifesto" aria-labelledby="about-title">
      <h1 id="about-title">About Until Every Cage is Empty</h1>
      <h2>The Project</h2>
      <p><strong>Until Every Cage is Empty</strong> is an instrument of exposure. We aggregate public government data to map the global infrastructure of animal exploitation. From slaughterhouses and vivisection labs to commercial breeders, we bring the industry's hidden network into a single, searchable interface.</p>

      <h2>The Reality</h2>
      <p>The violence inflicted on these animals is not accidental; it is <strong>standard industry practice</strong>. In the facilities mapped here, sentient beings endure systematic torture legalized by the state:</p>
      <ul>
        <li><strong>Routine Mutilation:</strong> Piglets are castrated and tails are docked without anesthesia. Cows are dehorned with burning irons. Chickens are debeaked with hot blades.</li>
        <li><strong>Total Confinement:</strong> Sows are bolted into gestation crates so small they cannot turn around. Hens are stacked in battery cages, denied the space to spread their wings for their entire lives.</li>
        <li><strong>Psychological Torture:</strong> Newborns are ripped from their mothers hours after birth. Male chicks, useless to the egg industry, are ground up alive or suffocated in trash bags.</li>
      </ul>

      <h2>The Architecture of Silence</h2>
      <p>The industry knows the public would never accept this reality if they saw it. Therefore, the system is engineered to ensure you never do.</p>
      <ul>
        <li><strong>Physical Erasure:</strong> Facilities are built in remote locations, housed in windowless bunkers, and surrounded by security perimeters to physically separate the consumer from the victim.</li>
        <li><strong>Legal Intimidation:</strong> "Ag-Gag" laws criminalize whistleblowing, making it a felony to photograph or record the abuse taking place inside these walls.</li>
        <li><strong>Humane-Washing:</strong> Labels like "Free Range" and "Locally Sourced" are marketing fabrications designed to soothe consumer guilt while hiding the industrialized slaughterhouse floor.</li>
      </ul>

      <h2>The Mission</h2>
      <p><strong>Transparency is resistance.</strong> By mapping this concealed infrastructure, we aim to:</p>
      <ul>
        <li><strong>Shatter Ignorance:</strong> Confront the public with the staggering scale of industrialized violence.</li>
        <li><strong>Arm the Movement:</strong> Provide investigators and activists with the location data needed to target campaigns and document violations.</li>
        <li><strong>Force Accountability:</strong> Ensure that no facility can hide its operations in the dark.</li>
      </ul>

      <h2>Get Involved</h2>
      <p>Contact, GitHub, Discord, Donate and Vegan Resources using the links above.</p>
      <h2>Until Every Cage is Empty</h2>
    </section>
    <aside class="about-counter-slot" aria-label="Animal counter"></aside>
  </div>
  <section id="sources" aria-labelledby="sources-title">
    <h2 id="sources-title">Sources and methods</h2>
    <p>Records retain their source origin, dates, location precision, and available evidence. Interpretation and connections are labeled separately. Coverage is incomplete: absence from the map does not show that a facility is absent or closed.</p>
    <p>Community submissions are separate from the project dataset.</p>
    <p>Facility points, approximate locality references, and records without a publishable point have different precision. We do not guess locations.</p>
    <p>Street maps use OpenStreetMap, satellite imagery uses Esri, and 3D terrain uses <a href="https://mapterhorn.com/attribution" target="_blank" rel="noreferrer">Mapterhorn</a>. Map providers receive your IP address and tile requests, not facility records or search text.</p>
    <p><a href={route('database/api')}>Browse public data and releases</a> · <a href={returnMapHref}>Open the map</a></p>
  </section>
</article>
<style>
  .about-page{width:min(100% - 3rem,72rem);margin:auto;padding:1.5rem 0 2.5rem;color:#f1efe8;font:.9rem/1.55 system-ui,sans-serif}
  .identity-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(18rem,24rem);gap:2rem;align-items:start}
  section{scroll-margin-top:1rem;margin:0 0 1.6rem}h1{margin:0 0 1.2rem;font:500 2rem/1.2 Georgia,serif;letter-spacing:-.02em}h2{margin:1.3rem 0 .45rem;font:600 1.12rem/1.35 system-ui,sans-serif}.manifesto h2:first-of-type{margin-top:0}p,li{color:#c6d0c5}p{margin:0 0 .7rem}ul{margin:.45rem 0 1rem;padding-left:1.2rem}li{margin:.35rem 0;padding-left:.2rem}.about-counter-slot{min-height:15rem}.about-page a{color:#dce8d9;text-underline-offset:.2em;overflow-wrap:anywhere}
  @media(max-width:48rem){.about-page{width:calc(100% - 2rem);padding-top:1.2rem}.identity-layout{grid-template-columns:1fr;gap:1rem}.about-counter-slot{min-height:0;grid-row:1}.manifesto{grid-row:2}h1{font-size:1.7rem}}
</style>
