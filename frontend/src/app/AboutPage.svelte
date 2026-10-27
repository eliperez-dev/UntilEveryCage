<script lang="ts">
  import FaqPage from './FaqPage.svelte';
  import type { AboutSection } from './routeState';
  let { section = 'overview', returnMapHref = '#/map' }: { section?: AboutSection; returnMapHref?: string } = $props();
  import AnimalKillCounter from './AnimalKillCounter.svelte';
  import { language, tr } from './language';
  const logo = `${import.meta.env.BASE_URL}assets/icon.png`;
</script>
<svelte:head><title>{tr('About', $language)} · Until Every Cage</title><meta name="description" content={tr('About the project Until Every Cage and its mission.', $language)} /></svelte:head>
<article class="about-page" aria-label={tr('About Until Every Cage', $language)}>
  <div class="identity-layout">
    <section id="overview" class="manifesto" aria-labelledby="about-title">
      <h1 id="about-title">{tr('About Until Every Cage is Empty', $language)}</h1>
      <h2>{tr('The Project', $language)}</h2>
      <p><strong>Until Every Cage is Empty</strong> {tr("is an instrument of exposure. We aggregate public government data to map the global infrastructure of animal exploitation. From slaughterhouses and vivisection labs to commercial breeders, we bring the industry's hidden network into a single, searchable interface.", $language)}</p>

      <h2>{tr('The Reality', $language)}</h2>
      <p>{tr('The violence inflicted on these animals is not accidental; it is', $language)} <strong>{tr('standard industry practice', $language)}</strong>{tr('. In the facilities mapped here, sentient beings endure systematic torture legalized by the state:', $language)}</p>
      <ul>
        <li><strong>{tr("Routine Mutilation:", $language)}</strong> {tr("Piglets are castrated and tails are docked without anesthesia. Cows are dehorned with burning irons. Chickens are debeaked with hot blades.", $language)}</li>
        <li><strong>{tr("Total Confinement:", $language)}</strong> {tr("Sows are bolted into gestation crates so small they cannot turn around. Hens are stacked in battery cages, denied the space to spread their wings for their entire lives.", $language)}</li>
        <li><strong>{tr("Psychological Torture:", $language)}</strong> {tr("Newborns are ripped from their mothers hours after birth. Male chicks, useless to the egg industry, are ground up alive or suffocated in trash bags.", $language)}</li>
      </ul>

      <h2>{tr('The Architecture of Silence', $language)}</h2>
      <p>{tr("The industry knows the public would never accept this reality if they saw it. Therefore, the system is engineered to ensure you never do.", $language)}</p>
      <ul>
        <li><strong>{tr("Physical Erasure:", $language)}</strong> {tr("Facilities are built in remote locations, housed in windowless bunkers, and surrounded by security perimeters to physically separate the consumer from the victim.", $language)}</li>
        <li><strong>{tr("Legal Intimidation:", $language)}</strong> {tr("\"Ag-Gag\" laws criminalize whistleblowing, making it a felony to photograph or record the abuse taking place inside these walls.", $language)}</li>
        <li><strong>{tr("Humane-Washing:", $language)}</strong> {tr("Labels like \"Free Range\" and \"Locally Sourced\" are marketing fabrications designed to soothe consumer guilt while hiding the industrialized slaughterhouse floor.", $language)}</li>
      </ul>

      <h2>{tr('The Mission', $language)}</h2>
      <p><strong>{tr("Transparency is resistance.", $language)}</strong> {tr("By mapping this concealed infrastructure, we aim to:", $language)}</p>
      <ul>
        <li><strong>{tr("Shatter Ignorance:", $language)}</strong> {tr("Confront the public with the staggering scale of industrialized violence.", $language)}</li>
        <li><strong>{tr("Arm the Movement:", $language)}</strong> {tr("Provide investigators and activists with the location data needed to target campaigns and document violations.", $language)}</li>
        <li><strong>{tr("Force Accountability:", $language)}</strong> {tr("Ensure that no facility can hide its operations in the dark.", $language)}</li>
      </ul>

      <h2>{tr('Get Involved', $language)}</h2>
      <p class="involvement-links"><a href="mailto:untileverycageproject@protonmail.com">{tr('Contact', $language)}</a> · <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">GitHub</a> · <a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noreferrer">Discord</a> · <a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">{tr('Donate', $language)}</a> · <a href="https://linktr.ee/veganresource" target="_blank" rel="noreferrer">{tr('Vegan resources', $language)}</a></p>
      <h2>{tr('Until Every Cage is Empty', $language)}</h2>
      <img class="about-logo" src={logo} alt={tr('Until Every Cage logo showing a world map marked with location pins', $language)} />
    </section>
    <aside class="about-counter-slot" aria-label={tr('Animal counter', $language)}><AnimalKillCounter /></aside>
  </div>
  <FaqPage embedded {returnMapHref} section={section === 'overview' || section === 'sources' ? undefined : section} />
</article>
<style>
  .about-page{width:min(100% - 3rem,72rem);margin:auto;padding:1.5rem 0 2.5rem;color:var(--ink);font:.9rem/1.55 system-ui,sans-serif}
  .identity-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(18rem,24rem);gap:2rem;align-items:start}
  section{scroll-margin-top:1rem;margin:0 0 1.6rem}h1{margin:0 0 1.2rem;font:500 2rem/1.2 Georgia,serif;letter-spacing:-.02em}h2{margin:1.3rem 0 .45rem;font:600 1.12rem/1.35 system-ui,sans-serif}.manifesto h2:first-of-type{margin-top:0}p,li{color:var(--ink-secondary)}p{margin:0 0 .7rem}ul{margin:.45rem 0 1rem;padding-left:1.2rem}li{margin:.35rem 0;padding-left:.2rem}.about-logo{display:block;width:4rem;height:4rem;object-fit:contain;margin:.4rem 0 0}.about-counter-slot{min-height:15rem}.about-page a{color:var(--link);text-underline-offset:.2em;overflow-wrap:anywhere}
  @media(max-width:48rem){.about-page{width:calc(100% - 2rem);padding-top:1.2rem}.identity-layout{grid-template-columns:1fr;gap:1rem}.about-counter-slot{min-height:0;grid-row:1}.manifesto{grid-row:2}h1{font-size:1.7rem}}
</style>
