<script lang="ts">
  import PreviewMasthead from './PreviewMasthead.svelte';
  import AboutSubnav from './AboutSubnav.svelte';

  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  let mapHref = $derived(returnMapHref);
  let databaseHref = $derived.by(() => returnMapHref.includes('?') ? `#/database?${returnMapHref.split('?')[1]}` : '#/database');
</script>

<svelte:head>
  <title>Sources & Methodology · Until Every Cage</title>
  <meta name="description" content="How Until Every Cage handles source evidence, map precision, publication, and corrections." />
</svelte:head>

<PreviewMasthead current="about" {mapHref} {databaseHref} />

<main id="main-content" class="methodology">
  <div class="page-frame">
    <AboutSubnav current="sources" {returnMapHref} />
    <header class="intro">
      <p class="eyebrow">Reading the map</p>
      <h1>Sources & Methodology</h1>
      <p class="lede">This map is a way into source-backed records, not a complete or independently verified inventory of facilities. The location shown for a record depends on the precision of the information available and eligible for display.</p>
    </header>

    <nav class="contents" aria-label="On this page">
      <span>On this page</span>
      <button type="button" onclick={() => document.getElementById('record-path')?.scrollIntoView()}>From source to map</button>
      <button type="button" onclick={() => document.getElementById('precision')?.scrollIntoView()}>Location precision</button>
      <button type="button" onclick={() => document.getElementById('limits')?.scrollIntoView()}>What records cannot prove</button>
      <button type="button" onclick={() => document.getElementById('corrections')?.scrollIntoView()}>Corrections & privacy</button>
    </nav>

    <section id="record-path" class="chapter" aria-labelledby="record-path-title">
      <div class="chapter-label">01 / Process</div>
      <div class="chapter-body">
        <h2 id="record-path-title">How a record reaches the map</h2>
        <p>Each displayed entry begins with a source observation. The project interprets that observation, assesses what kind of activity it describes, and identifies whether its location is suitable to show. A release decision determines what becomes available in a particular public view.</p>
        <ol class="process">
          <li><strong>Source</strong><span>An observation has an origin and, when known, observation and retrieval dates. A government source is still a source—not a project approval.</span></li>
          <li><strong>Interpretation</strong><span>Names, activity labels, and possible connections can involve project classification. An interpretation is not an original source statement.</span></li>
          <li><strong>Location</strong><span>A coordinate may describe a facility, a locality such as a commune or municipality, or no publishable point at all.</span></li>
          <li><strong>Release</strong><span>Review, privacy screening, project approval, and publication are separate decisions. Availability in one release does not guarantee the claim is true or current.</span></li>
        </ol>
      </div>
    </section>

    <section id="precision" class="chapter" aria-labelledby="precision-title">
      <div class="chapter-label">02 / Position</div>
      <div class="chapter-body">
        <h2 id="precision-title">What a point means</h2>
        <p>The map deliberately distinguishes these states. Zoom level, satellite imagery, and a neat-looking symbol do not improve the evidence behind a location.</p>
        <p>Maps use OpenStreetMap tiles; viewing a map contacts the tile provider. Placing a pin supplies the chosen location directly.</p>
        <dl class="precision-ladder">
          <div><dt><span class="ladder-index">A</span> Mapped at a facility coordinate</dt><dd>A published coordinate associated with the record. Its source and precision still matter; a displayed point is not a guarantee that it identifies the operating site.</dd></div>
          <div><dt><span class="ladder-index">B</span> Mapped to a locality reference</dt><dd>An approximate city, commune, municipality, or postal reference. A centroid is <em>not</em> a facility point. A circular halo on the map is a visual aid, not a measured uncertainty boundary.</dd></div>
          <div><dt><span class="ladder-index">C</span> Searchable without a map point</dt><dd>The record may be available in search or the database without a publishable coordinate. It is not placed at a guessed location.</dd></div>
        </dl>
      </div>
    </section>

    <section id="limits" class="chapter" aria-labelledby="limits-title">
      <div class="chapter-label">03 / Limits</div>
      <div class="chapter-body">
        <h2 id="limits-title">What inclusion cannot establish</h2>
        <p>Sources differ in scope, age, and quality. A missing entry does not prove there is no facility; an included entry does not independently prove current operation, an exact operating address, ownership, a supply-chain relationship, or wrongdoing.</p>
        <p>Connections between records may be source-supported or inferred from stated signals. An inferred connection is a lead for investigation, not proof of ownership, identity, or activity between two facilities.</p>
      </div>
    </section>

    <section class="chapter" aria-labelledby="coverage-title">
      <div class="chapter-label">04 / Coverage</div>
      <div class="chapter-body">
        <h2 id="coverage-title">Sources and coverage</h2>
        <p>Coverage reflects the sources included in the selected release and the records eligible for that view. It is not a census. Source origin, dates, and available evidence should be read on the individual record where supplied; this page does not imply a fixed worldwide source inventory or a live record count.</p>
        <p><a href="#/database">Explore available records in the Database <span aria-hidden="true">↗</span></a></p>
      </div>
    </section>

    <section id="corrections" class="chapter corrections" aria-labelledby="corrections-title">
      <div class="chapter-label">05 / Response</div>
      <div class="chapter-body">
        <h2 id="corrections-title">Corrections & privacy</h2>
        <p>If a record is wrong, identifies a residence, maps the wrong property, or exposes a person, contact <a href="mailto:untileverycageproject@protonmail.com">untileverycageproject@protonmail.com</a>. Include the public record link or ID and a brief description of the concern. For a location-exposure concern, put “Privacy/location removal” in the subject.</p>
        <p>Please do not put sensitive evidence in a public issue or send more personal information than needed to explain the concern.</p>
      </div>
    </section>
  </div>
</main>

<style>
  :global(body) { margin:0; background:#171a18; color:#f1efe8; }
  .methodology { min-height:calc(100dvh - 4.8rem); font-family:ui-sans-serif,system-ui,sans-serif; background:#171a18; color:#f1efe8; }
  .page-frame { width:min(100% - 3rem, 74rem); margin:auto; padding:clamp(2.5rem,6vw,5rem) 0 7rem; }
  .intro { max-width:49rem; padding-bottom:3.5rem; }
  .eyebrow,.chapter-label,.contents span { color:#9eafa2; font-size:.7rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
  h1 { margin:.8rem 0 1.4rem; font:400 clamp(2.6rem,6vw,5rem)/1.06 Georgia,serif; letter-spacing:-.035em; }
  .lede { margin:0; color:#d3dbd1; font-size:clamp(1.03rem,1.6vw,1.28rem); line-height:1.65; }
  .contents { display:flex; flex-wrap:wrap; align-items:baseline; gap:.65rem 1.35rem; padding:1.1rem 0; border-top:1px solid #4a554b; border-bottom:1px solid #4a554b; }
  .contents span { margin-right:1rem; }
  a { color:#dce8d9; text-underline-offset:.25em; }
  a:hover { color:#fff; }
  a:focus-visible, button:focus-visible { outline:2px solid #f1efe8; outline-offset:4px; }
  .contents button { padding:0 0 .15rem; border:0; border-bottom:1px solid #6a786c; background:none; color:#dce8d9; font:inherit; font-size:.8rem; cursor:pointer; }
  .contents button:hover { color:#fff; }
  .chapter { display:grid; grid-template-columns:minmax(10rem, 1fr) minmax(0, 3fr); gap:2rem; padding:3rem 0; border-bottom:1px solid #3c463e; scroll-margin-top:2rem; }
  .chapter-label { padding-top:.4rem; }
  .chapter-body { max-width:49rem; }
  h2 { margin:0 0 1.25rem; font:400 clamp(1.65rem,3vw,2.45rem)/1.15 Georgia,serif; letter-spacing:-.02em; }
  p { line-height:1.7; }
  .chapter-body > p { max-width:43rem; margin:0 0 1rem; color:#c6d0c5; font-size:.96rem; }
  .process { list-style:none; margin:2rem 0 0; padding:0; counter-reset:step; }
  .process li { display:grid; grid-template-columns:minmax(7rem, 1fr) minmax(0,3fr); gap:1rem; padding:1rem 0; border-top:1px solid #414a42; }
  .process li strong { color:#f1efe8; font-size:.87rem; }
  .process li span { color:#bac8bb; line-height:1.55; font-size:.88rem; }
  .precision-ladder { margin:2rem 0 0; }
  .precision-ladder > div { display:grid; grid-template-columns:minmax(12rem, 1.5fr) minmax(0, 2fr); gap:1.25rem; padding:1.35rem 0; border-top:1px solid #637268; }
  .precision-ladder dt { display:flex; gap:.75rem; font-size:.96rem; font-weight:650; line-height:1.35; }
  .ladder-index { display:inline-grid; place-content:center; flex:none; width:1.5rem; height:1.5rem; border:1px solid #8fa392; color:#b9cebc; font:700 .65rem ui-sans-serif,system-ui; }
  .precision-ladder dd { margin:0; color:#bec9bf; font-size:.89rem; line-height:1.6; }
  .corrections { border-bottom:0; }
  @media (max-width:45rem) {
    .page-frame { width:min(100% - 2rem, 74rem); padding-top:2.5rem; }
    .intro { padding-bottom:2.2rem; }
    .chapter { display:block; padding:2.4rem 0; }
    .chapter-label { margin-bottom:1.1rem; }
    .process li,.precision-ladder > div { grid-template-columns:1fr; gap:.45rem; }
  }
</style>
