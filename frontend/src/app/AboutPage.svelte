<script lang="ts">
  import AnimalKillCounter from './AnimalKillCounter.svelte';
  import { language, tr } from './language';
  const logo = `${import.meta.env.BASE_URL}assets/icon.png`;
</script>
<svelte:head><title>About · Until Every Cage</title><meta name="description" content="About the project Until Every Cage and its mission." /></svelte:head>
<article class="about-page" aria-label={tr('About Until Every Cage is Empty', $language)}>
  <div class="identity-layout">
    <section id="overview" class="manifesto" aria-labelledby="about-title">
      <h1 id="about-title">{tr('About Until Every Cage is Empty', $language)}</h1>
      <h2>{tr('The Project', $language)}</h2>
      <p><strong>Until Every Cage is Empty</strong> {#if $language === 'es'}es una herramienta para visibilizar. Reunimos datos públicos gubernamentales para cartografiar la infraestructura mundial de explotación animal. Desde mataderos y laboratorios de vivisección hasta criaderos comerciales, reunimos la red oculta de la industria en una sola interfaz con búsqueda.{:else}is an instrument of exposure. We aggregate public government data to map the global infrastructure of animal exploitation. From slaughterhouses and vivisection labs to commercial breeders, we bring the industry's hidden network into a single, searchable interface.{/if}</p>

      <h2>{tr('The Reality', $language)}</h2>
      <p>{#if $language === 'es'}La violencia infligida a estos animales no es accidental; es <strong>una práctica habitual de la industria</strong>. En las instalaciones cartografiadas aquí, seres sintientes soportan tortura sistemática legalizada por el Estado:{:else}The violence inflicted on these animals is not accidental; it is <strong>standard industry practice</strong>. In the facilities mapped here, sentient beings endure systematic torture legalized by the state:{/if}</p>
      <ul>
        <li>{#if $language === 'es'}<strong>Mutilación rutinaria:</strong> A los lechones se les castra y corta la cola sin anestesia. A las vacas se les quitan los cuernos con hierros candentes. A las gallinas se les recorta el pico con cuchillas calientes.{:else}<strong>Routine Mutilation:</strong> Piglets are castrated and tails are docked without anesthesia. Cows are dehorned with burning irons. Chickens are debeaked with hot blades.{/if}</li>
        <li>{#if $language === 'es'}<strong>Confinamiento total:</strong> Las cerdas quedan inmovilizadas en jaulas de gestación tan pequeñas que no pueden darse la vuelta. Las gallinas se apilan en jaulas en batería y se les niega espacio para extender las alas durante toda su vida.{:else}<strong>Total Confinement:</strong> Sows are bolted into gestation crates so small they cannot turn around. Hens are stacked in battery cages, denied the space to spread their wings for their entire lives.{/if}</li>
        <li>{#if $language === 'es'}<strong>Tortura psicológica:</strong> Las crías son separadas de sus madres pocas horas después de nacer. Los pollitos macho, inútiles para la industria del huevo, son triturados vivos o asfixiados en bolsas de basura.{:else}<strong>Psychological Torture:</strong> Newborns are ripped from their mothers hours after birth. Male chicks, useless to the egg industry, are ground up alive or suffocated in trash bags.{/if}</li>
      </ul>

      <h2>{tr('The Architecture of Silence', $language)}</h2>
      <p>{#if $language === 'es'}La industria sabe que el público nunca aceptaría esta realidad si la viera. Por eso, el sistema está diseñado para que nunca la veas.{:else}The industry knows the public would never accept this reality if they saw it. Therefore, the system is engineered to ensure you never do.{/if}</p>
      <ul>
        <li>{#if $language === 'es'}<strong>Borrado físico:</strong> Las instalaciones se construyen en lugares remotos, dentro de búnkeres sin ventanas y rodeadas de perímetros de seguridad para separar físicamente al consumidor de la víctima.{:else}<strong>Physical Erasure:</strong> Facilities are built in remote locations, housed in windowless bunkers, and surrounded by security perimeters to physically separate the consumer from the victim.{/if}</li>
        <li>{#if $language === 'es'}<strong>Intimidación legal:</strong> Las leyes «Ag-Gag» criminalizan las denuncias y convierten en delito grave fotografiar o grabar los abusos que ocurren tras estos muros.{:else}<strong>Legal Intimidation:</strong> "Ag-Gag" laws criminalize whistleblowing, making it a felony to photograph or record the abuse taking place inside these walls.{/if}</li>
        <li>{#if $language === 'es'}<strong>Lavado de imagen humanitario:</strong> Etiquetas como «campero» y «de origen local» son invenciones publicitarias diseñadas para aliviar la culpa del consumidor mientras ocultan la realidad de los mataderos industriales.{:else}<strong>Humane-Washing:</strong> Labels like "Free Range" and "Locally Sourced" are marketing fabrications designed to soothe consumer guilt while hiding the industrialized slaughterhouse floor.{/if}</li>
      </ul>

      <h2>{tr('The Mission', $language)}</h2>
      <p>{#if $language === 'es'}<strong>La transparencia es resistencia.</strong> Al cartografiar esta infraestructura oculta, buscamos:{:else}<strong>Transparency is resistance.</strong> By mapping this concealed infrastructure, we aim to:{/if}</p>
      <ul>
        <li>{#if $language === 'es'}<strong>Romper la ignorancia:</strong> Enfrentar al público con la enorme escala de la violencia industrializada.{:else}<strong>Shatter Ignorance:</strong> Confront the public with the staggering scale of industrialized violence.{/if}</li>
        <li>{#if $language === 'es'}<strong>Dar herramientas al movimiento:</strong> Proporcionar a investigadores y activistas datos de ubicación para orientar campañas y documentar infracciones.{:else}<strong>Arm the Movement:</strong> Provide investigators and activists with the location data needed to target campaigns and document violations.{/if}</li>
        <li>{#if $language === 'es'}<strong>Exigir responsabilidades:</strong> Lograr que ninguna instalación pueda ocultar sus operaciones en la oscuridad.{:else}<strong>Force Accountability:</strong> Ensure that no facility can hide its operations in the dark.{/if}</li>
      </ul>

      <h2>{tr('Get Involved', $language)}</h2>
      <p class="involvement-links"><a href="mailto:untileverycageproject@protonmail.com">{tr('Contact', $language)}</a> · <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">GitHub</a> · <a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noreferrer">Discord</a> · <a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">{tr('Donate', $language)}</a> · <a href="https://linktr.ee/veganresource" target="_blank" rel="noreferrer">{tr('Vegan resources', $language)}</a></p>
      <h2>{tr('Until Every Cage is Empty', $language)}</h2>
      <img class="about-logo" src={logo} alt="Until Every Cage logo showing a world map marked with location pins" />
    </section>
    <aside class="about-counter-slot" aria-label="Animal counter"><AnimalKillCounter /></aside>
  </div>
</article>
<style>
  .about-page{width:min(100% - 3rem,72rem);margin:auto;padding:1.5rem 0 2.5rem;color:#f1efe8;font:.9rem/1.55 system-ui,sans-serif}
  .identity-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(18rem,24rem);gap:2rem;align-items:start}
  section{scroll-margin-top:1rem;margin:0 0 1.6rem}h1{margin:0 0 1.2rem;font:500 2rem/1.2 Georgia,serif;letter-spacing:-.02em}h2{margin:1.3rem 0 .45rem;font:600 1.12rem/1.35 system-ui,sans-serif}.manifesto h2:first-of-type{margin-top:0}p,li{color:#c6d0c5}p{margin:0 0 .7rem}ul{margin:.45rem 0 1rem;padding-left:1.2rem}li{margin:.35rem 0;padding-left:.2rem}.about-logo{display:block;width:4rem;height:4rem;object-fit:contain;margin:.4rem 0 0}.about-counter-slot{min-height:15rem}.about-page a{color:#dce8d9;text-underline-offset:.2em;overflow-wrap:anywhere}
  @media(max-width:48rem){.about-page{width:calc(100% - 2rem);padding-top:1.2rem}.identity-layout{grid-template-columns:1fr;gap:1rem}.about-counter-slot{min-height:0;grid-row:1}.manifesto{grid-row:2}h1{font-size:1.7rem}}
</style>
