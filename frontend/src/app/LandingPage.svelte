<script lang="ts">
  import { onMount } from 'svelte';
  import { language, tr } from './language';
  import PreviewMasthead from './PreviewMasthead.svelte';
  import pig from '../assets/landing/pig.jpg';
  import cow from '../assets/landing/cow.jpg';
  import mapPreview from '../assets/landing/map-preview.jpg';

  let { mapHref = '#/map' }: { mapHref?: string } = $props();
  const databaseHref = $derived.by(() => {
    const query = mapHref.split('?')[1];
    return query ? `#/database?${query}` : '#/database';
  });
  let paused = $state(false);
  let reducedMotion = $state(true);
  let pageHidden = $state(false);

  onMount(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const syncPreference = () => reducedMotion = preference.matches;
    const syncVisibility = () => pageHidden = document.hidden;
    syncPreference();
    syncVisibility();
    preference.addEventListener('change', syncPreference);
    document.addEventListener('visibilitychange', syncVisibility);
    return () => {
      preference.removeEventListener('change', syncPreference);
      document.removeEventListener('visibilitychange', syncVisibility);
    };
  });
</script>

{#snippet arrow()}
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17 17 7M7 7h10v10" /></svg>
{/snippet}

<div class="landing-page">
  <a class="skip-link" href="#landing-content" onclick={event => { event.preventDefault(); document.getElementById('landing-content')?.focus(); }}>{tr('Skip to content', $language)}</a>
  <PreviewMasthead current="landing" {mapHref} {databaseHref} />
  <main id="landing-content" tabindex="-1">
    <section class="hero" class:paused={paused || pageHidden} class:reduced-motion={reducedMotion} aria-labelledby="landing-title">
      <div class="hero-media">
        <img class="hero-photo pig" src={pig} alt={tr('A pig looking through the bars of a confinement crate', $language)} width="1200" height="630" fetchpriority="high" />
        <img class="hero-photo cow" src={cow} alt={tr('A calf with its mouth open among other calves', $language)} width="1920" height="800" />
      </div>
      <div class="shade" aria-hidden="true"></div>
      <div class="hero-copy">
        <h1 id="landing-title">{tr('HIDDEN IN', $language)}<br />{tr('PLAIN SIGHT.', $language)}</h1>
        <p>{tr('Behind closed doors, animals are bred, confined, experimented on and killed. Until Every Cage maps the industries responsible.', $language)}</p>
        <a class="action" href={mapHref}>{tr('Open the map', $language)} {@render arrow()}</a>
      </div>
      {#if !reducedMotion}
        <button class="motion-toggle" type="button" aria-label={tr(paused ? 'Resume background animation' : 'Pause background animation', $language)} title={tr(paused ? 'Resume background animation' : 'Pause background animation', $language)} onclick={() => paused = !paused}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">{#if paused}<path d="m9 5 10 7-10 7Z" />{:else}<path d="M9 5v14M15 5v14" />{/if}</svg>
        </button>
      {/if}
    </section>
    <section class="discovery" aria-labelledby="discovery-title">
      <div class="discovery-heading">
        <h2 id="discovery-title">{tr('See how far', $language)}<br />{tr('it reaches.', $language)}</h2>
        <p>{tr('Explore farms, slaughterhouses, laboratories and the businesses around them.', $language)}</p>
      </div>
      <div class="preview-frame">
        <a class="preview" href={mapHref} aria-label={tr('Open the map', $language)}>
          <img src={mapPreview} alt={tr('Preview of the Until Every Cage map, showing clusters across Europe and North America', $language)} width="1280" height="720" loading="lazy" />
          <span class="preview-action">{tr('Open the map', $language)} {@render arrow()}</span>
        </a>
        <small class="map-attribution"><a href="https://www.esri.com/" target="_blank" rel="noreferrer">Transportation © Esri</a> | <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a></small>
      </div>
    </section>
  </main>
  <footer class="landing-footer">
    <span>{tr('Until every cage is empty.', $language)}</span>
    <div><a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">{tr('Source code', $language)}</a><a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">{tr('Support the project', $language)}</a></div>
  </footer>
</div>

<style>
  .landing-page{--landing-bg:#f2f0e8;--landing-ink:#19221a;--landing-muted:#596359;--landing-line:#d0d4c8;--photo-ink:#f5f1e6;--button-bg:#eee9d9;position:relative;font:14px/1.5 system-ui,sans-serif;color:var(--landing-ink);background:var(--landing-bg)}
  main{min-height:0;padding:0;outline:none;color-scheme:light}
  a{color:inherit;text-decoration:none}a:hover{text-decoration:underline;text-underline-offset:5px}
  a:focus-visible,button:focus-visible{outline:3px solid #c78e50;outline-offset:5px}
  .skip-link{position:absolute;top:12px;left:16px;z-index:25;padding:12px 16px;background:var(--button-bg);color:var(--landing-ink);transform:translateY(-160%)}.skip-link:focus{transform:translateY(0)}
  svg{width:17px;height:17px;flex-shrink:0}
  .hero{position:relative;min-height:650px;isolation:isolate;overflow:hidden;background:#141414;color:var(--photo-ink)}
  .hero-media{position:absolute;inset:0;z-index:-3;overflow:hidden}.hero-photo{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:65% center;animation:slow-pan 28s linear infinite alternate;will-change:transform}.cow{opacity:0;object-position:62% center;animation:slow-pan 28s linear infinite alternate,crossfade 28s linear infinite;will-change:transform,opacity}
  .shade{position:absolute;inset:0;z-index:-2;background:linear-gradient(90deg,rgba(5,10,6,.92) 0%,rgba(5,10,6,.62) 34%,rgba(5,10,6,.08) 78%),linear-gradient(0deg,rgba(5,10,6,.46),transparent 45%,rgba(5,10,6,.46))}
  .hero-copy{padding:116px 48px 68px;max-width:660px}
  h1{font:500 clamp(58px,7.1vw,88px)/.91 system-ui,sans-serif;letter-spacing:-.065em;margin:0 0 30px;max-width:11ch}
  .hero-copy p{max-width:39ch;font-size:16px;line-height:1.6;margin:0 0 30px;color:var(--photo-ink)}
  .action{display:inline-flex;gap:32px;align-items:center;min-height:48px;padding:13px 20px;color:#171d17;background:var(--button-bg);font-weight:500}.action:hover{background:#fffbed;text-decoration:none}
  .motion-toggle{position:absolute;right:24px;bottom:22px;display:grid;place-items:center;width:44px;height:44px;min-height:44px;padding:0;color:var(--photo-ink);background:#14141499;border:1px solid #f5f1e680;border-radius:0}.motion-toggle:hover{background:#141414e6}.motion-toggle svg{width:21px;height:21px}
  .paused .hero-photo{animation-play-state:paused}.reduced-motion .hero-photo{animation:none;will-change:auto}.reduced-motion .cow{display:none}
  .discovery{padding:64px 48px 56px}.discovery-heading{display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:end;margin-bottom:34px}
  h2{font:400 clamp(34px,4.5vw,52px)/1.02 Georgia,serif;letter-spacing:-.035em;margin:0}.discovery-heading p{max-width:38ch;margin:0 0 14px;font-size:16px;line-height:1.55;color:var(--landing-muted)}
  .preview-frame{position:relative}.preview{position:relative;display:block;overflow:hidden;height:350px;border:1px solid var(--landing-line);background:#a8d3df}.preview>img{display:block;width:100%;height:112%;margin-top:-4%;object-fit:cover;object-position:center}
  .preview-action{position:absolute;right:18px;bottom:18px;display:flex;align-items:center;gap:28px;padding:12px 16px;min-height:44px;background:var(--landing-bg);color:var(--landing-ink);font-weight:500}.preview:hover .preview-action,.preview:focus-visible .preview-action{text-decoration:underline;text-underline-offset:4px}
  .map-attribution{position:absolute;bottom:1px;left:1px;max-width:calc(100% - 2px);padding:1px 4px;background:#f2f0e8ed;color:#263529;font-size:10px;line-height:1.3}
  .landing-footer{color-scheme:light;padding:27px 48px;border-top:1px solid var(--landing-line);display:flex;gap:24px;align-items:center;justify-content:space-between}.landing-footer>span{font:400 23px Georgia,serif}.landing-footer>div{display:flex;gap:24px;font-size:12px;color:var(--landing-muted)}.landing-footer a{display:flex;align-items:center;min-height:44px}
  @keyframes slow-pan{from{transform:scale(1.02) translateX(.3%)}to{transform:scale(1.08) translateX(-.5%)}}
  @keyframes crossfade{0%,43%{opacity:0}50%,93%{opacity:1}100%{opacity:0}}
  @media(prefers-reduced-motion:reduce){.hero-photo{animation:none;will-change:auto}.cow,.motion-toggle{display:none}}
  @media(max-width:700px){.hero{min-height:650px}.hero-photo{object-position:40% center}.cow{object-position:40% center}.shade{background:linear-gradient(0deg,rgba(5,10,6,.96),rgba(5,10,6,.75) 38%,rgba(5,10,6,.05) 78%,rgba(5,10,6,.56))}.hero-copy{padding:214px 24px 42px;max-width:440px}h1{font-size:clamp(38px,11.8vw,66px);letter-spacing:-.06em;margin-bottom:22px}.hero-copy p{font-size:14px;max-width:38ch;margin-bottom:24px}.motion-toggle{right:20px;bottom:20px}.discovery{padding:38px 24px}.discovery-heading{grid-template-columns:minmax(0,1fr);gap:22px;margin-bottom:26px}h2{font-size:38px}.discovery-heading p{font-size:14px}.preview{height:290px}.preview>img{width:185%;max-width:none;height:100%;margin-top:0;margin-left:-40%;object-position:center}.preview-action{right:10px;bottom:20px;font-size:12px;gap:18px}.landing-footer{color-scheme:light;padding:24px;align-items:flex-start;flex-direction:column;gap:8px}.landing-footer>span{font-size:22px}}
</style>
