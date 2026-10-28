<script lang="ts">
  import { onMount } from 'svelte';
  import { language } from '../language';
  import { storyMessages } from './messages';
  import { ActiveStoryClock, funnelParticles, gridParticles, STORY_RATES, type StoryMode, type StoryPopulation } from './engine';
  import { FISH_2019, LAND_ANIMALS_2024, poolsForIndividuals } from './comparisons';

  let { mapHref = '#/map' }: { mapHref?: string } = $props();
  const text = $derived(storyMessages($language));
  let population = $state<StoryPopulation>('land');
  let mode = $state<StoryMode>('funnel');
  let paused = $state(false);
  let reduced = $state(true);
  let oneKilled = $state(false);
  let canvas: HTMLCanvasElement;
  let one: HTMLDivElement;
  const lowerPools = $derived(Math.round(poolsForIndividuals(population === 'land' ? LAND_ANIMALS_2024 : FISH_2019[0])));
  const upperPools = $derived(Math.round(poolsForIndividuals(population === 'land' ? LAND_ANIMALS_2024 : FISH_2019[1])));
  let runtime: { select: (value: StoryPopulation) => void; redraw: () => void; sync: () => void } | null = null;

  function choosePopulation(value: StoryPopulation) {
    if (population === value) return;
    population = value;
    runtime?.select(value);
  }
  function chooseMode(value: StoryMode) { mode = value; runtime?.redraw(); }
  function togglePause() { paused = !paused; runtime?.sync(); }

  onMount(() => {
    const clock = new ActiveStoryClock(), oneClock = new ActiveStoryClock();
    const preference = matchMedia('(prefers-reduced-motion: reduce)');
    const context = canvas.getContext('2d');
    if (!context) return;
    const capacity = 160000;
    const whites = new Float32Array(capacity * 2), reds = new Float32Array(capacity * 2);
    let whiteCount = 0, redCount = 0;
    let width = 1, height = 1, ratio = 1, visible = false, oneVisible = false;
    let pixelImage: ImageData | null = null, pixels: Uint32Array | null = null;
    let frame = 0, disposed = false, lastDiagnostic = 0, populationEpoch = 0;
    const visit = (_id: number, x: number, y: number, dead: boolean) => {
      const buffer = dead ? reds : whites;
      const index = dead ? redCount++ : whiteCount++;
      buffer[index * 2] = x; buffer[index * 2 + 1] = y;
    };
    function drawDots(points: Float32Array, count: number, color: string) {
      context!.fillStyle = color;
      const radius = width < 500 ? 1.1 : 1.55;
      context!.beginPath();
      for (let i = 0; i < count; i++) {
        const x = points[i * 2]!, y = points[i * 2 + 1]!;
        context!.moveTo(x + radius, y); context!.arc(x, y, radius, 0, Math.PI * 2);
      }
      context!.fill();
    }
    function pixelDots(points: Float32Array, count: number, color: number, left: number) {
      const pixelWidth = canvas.width, pixelHeight = canvas.height, size = ratio > 1 ? 2 : 1;
      for (let i = 0; i < count; i++) {
        const x = Math.round((left + points[i * 2]!) * ratio), y = Math.round(points[i * 2 + 1]! * ratio);
        if (x < 0 || y < 0 || x + size > pixelWidth || y + size > pixelHeight) continue;
        const index = y * pixelWidth + x;
        pixels![index] = color;
        if (size === 2) { pixels![index + 1] = color; pixels![index + pixelWidth] = color; pixels![index + pixelWidth + 1] = color; }
      }
    }
    function render() {
      if (disposed) return;
      context!.clearRect(0, 0, width, height);
      const humanWidth = Math.max(62, width * .20), animalLeft = humanWidth + 18, animalWidth = width - animalLeft;
      const humanSeconds = reduced ? 1.68 : clock.elapsed;
      const seconds = reduced ? 1.68 : clock.elapsed - populationEpoch;
      whiteCount = 0; redCount = 0;
      const particles = mode === 'funnel' ? funnelParticles : gridParticles;
      particles(seconds, STORY_RATES[population], animalWidth, height, visit);
      if (population === 'fish' && pixelImage && pixels) {
        pixels.fill(0);
        pixelDots(whites, whiteCount, 0xffe8f0f2, animalLeft);
        pixelDots(reds, redCount, 0xff4947d7, animalLeft);
        context!.putImageData(pixelImage, 0, 0);
      }
      context!.strokeStyle = '#f2f0e82c'; context!.lineWidth = 1;
      context!.beginPath(); context!.moveTo(humanWidth + 8, 0); context!.lineTo(humanWidth + 8, height); context!.stroke();
      funnelParticles(humanSeconds, 2, humanWidth, height, (_id, x, y, dead) => {
        context!.strokeStyle = dead ? '#d74749' : '#f2f0e8'; context!.fillStyle = context!.strokeStyle;
        context!.lineWidth = 1.2;
        context!.beginPath(); context!.arc(x, y - 5, 2.5, 0, Math.PI * 2); context!.fill();
        context!.beginPath(); context!.moveTo(x, y - 1); context!.lineTo(x, y + 7);
        context!.moveTo(x - 4, y + 2); context!.lineTo(x + 4, y + 2);
        context!.moveTo(x - 3, y + 13); context!.lineTo(x, y + 7); context!.lineTo(x + 3, y + 13); context!.stroke();
      });
      context!.save(); context!.translate(animalLeft, 0);
      if (mode === 'funnel') {
        context!.strokeStyle = '#f2f0e84a'; context!.lineWidth = 1;
        context!.beginPath();
        context!.moveTo(animalWidth * .055, 8);
        context!.bezierCurveTo(animalWidth * .11, height * .38, animalWidth * .44, height * .36, animalWidth * .482, height * .53);
        context!.moveTo(animalWidth * .945, 8);
        context!.bezierCurveTo(animalWidth * .89, height * .38, animalWidth * .56, height * .36, animalWidth * .518, height * .53);
        context!.stroke();
      }
      if (population === 'land') { drawDots(whites, whiteCount, '#f2f0e8'); drawDots(reds, redCount, '#d74749'); }
      context!.restore();
    }
    function resize() {
      const rect = canvas.getBoundingClientRect();
      width = Math.max(1, rect.width); height = Math.max(1, rect.height);
      ratio = Math.min(2, devicePixelRatio || 1);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      pixelImage = context!.createImageData(canvas.width, canvas.height);
      pixels = new Uint32Array(pixelImage.data.buffer);
      context!.setTransform(ratio, 0, 0, ratio, 0, 0); render();
    }
    function shouldRun() { return !disposed && !document.hidden && !reduced && ((!paused && visible) || (oneVisible && !oneKilled)); }
    function publishCounts() {
      canvas.dataset.emitted = String(Math.floor((clock.elapsed - populationEpoch) * STORY_RATES[population]));
      canvas.dataset.humanEmitted = String(clock.emitted(2));
    }
    function tick(now: number) {
      frame = 0;
      if (!shouldRun()) return;
      clock.advance(now); oneClock.advance(now);
      if (oneClock.elapsed >= .9) oneKilled = true;
      if (visible && !paused) render();
      if (now - lastDiagnostic > 250) {
        publishCounts();
        lastDiagnostic = now;
      }
      if (shouldRun()) frame = requestAnimationFrame(tick);
    }
    function sync() {
      const now = performance.now();
      clock.setRunning(!disposed && !document.hidden && !reduced && !paused && visible, now);
      oneClock.setRunning(!disposed && !document.hidden && !reduced && oneVisible && !oneKilled, now);
      publishCounts();
      canvas.dataset.state = reduced ? 'static' : paused ? 'paused' : visible && !document.hidden ? 'running' : 'offscreen';
      if (shouldRun()) { if (!frame) frame = requestAnimationFrame(tick); }
      else { cancelAnimationFrame(frame); frame = 0; }
    }
    function syncPreference() { reduced = preference.matches; if (reduced) oneKilled = true; sync(); render(); }
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.target === canvas) visible = entry.isIntersecting;
        else oneVisible = entry.isIntersecting;
      }
      sync();
    }, { threshold: 0 });
    const resizeObserver = new ResizeObserver(resize);
    observer.observe(canvas); observer.observe(one); resizeObserver.observe(canvas);
    preference.addEventListener('change', syncPreference);
    document.addEventListener('visibilitychange', sync);
    runtime = { select: () => { clock.advance(performance.now()); populationEpoch = clock.elapsed; canvas.dataset.emitted = '0'; render(); }, redraw: render, sync };
    syncPreference(); resize();
    return () => {
      disposed = true; runtime = null; cancelAnimationFrame(frame);
      observer.disconnect(); resizeObserver.disconnect();
      preference.removeEventListener('change', syncPreference);
      document.removeEventListener('visibilitychange', sync);
      clock.setRunning(false, performance.now()); oneClock.setRunning(false, performance.now());
      // Release the backing canvas and typed-array closure on route departure.
      canvas.width = 1; canvas.height = 1;
      pixelImage = null; pixels = null;
    };
  });
</script>

<section class="scale-story" id="landing-scale-story" aria-labelledby="scale-story-title" tabindex="-1">
  <div class="story-intro">
    <h2 id="scale-story-title">{text.startWithOne}</h2>
    <div class="one-animal" bind:this={one} role="img" aria-label={`${text.oneAnimal} ${oneKilled ? text.killed : text.alive}`}>
      <span class="one-dot" class:dead={oneKilled} aria-hidden="true"></span>
      <span>{text.oneAnimal}</span><small>{oneKilled ? text.killed : text.alive}</small>
    </div>
  </div>
  <div class="story-heading"><h3>{text.oneSecond}</h3>
    <div class="segmented" role="group" aria-label={text.population}>
      <button type="button" aria-pressed={population === 'land'} onclick={() => choosePopulation('land')}>{text.land}</button>
      <button type="button" aria-pressed={population === 'fish'} onclick={() => choosePopulation('fish')}>{text.fish}</button>
    </div>
  </div>
  <div class="rate-row">
    <div><p class="rate">{population === 'land' ? '2,779' : '33,500–65,700'}<span>{population === 'land' ? text.animalsPerSecond : text.fishPerSecond}</span></p>
      <p class="rate-date">{population === 'land' ? text.landDate : text.fishDate}</p>
    </div>
    <div class="segmented mode" role="group" aria-label={text.visualization}>
      <button type="button" aria-pressed={mode === 'funnel'} onclick={() => chooseMode('funnel')}>{text.funnel}</button>
      <button type="button" aria-pressed={mode === 'grid'} onclick={() => chooseMode('grid')}>{text.grid}</button>
    </div>
  </div>
  <div class="lane-labels"><div><strong>{text.humans}</strong><span aria-label={text.humanRate}>2 / s</span></div><div><strong>{population === 'land' ? text.land : text.fish}</strong><span>{population === 'land' ? '2,779' : '65,671'} / s</span></div></div>
  <p class="human-context">{text.humans}: {text.humanActivity} · {text.humanDate}</p>
  <div class="canvas-wrap" data-mode={mode} data-population={population} role="img" aria-label={`${population === 'land' ? text.landCanvas : text.fishCanvas} ${text.humanCanvas}`}>
    <canvas bind:this={canvas} aria-hidden="true"></canvas>
  </div>
  <div class="story-controls">
    <div class="legend"><span><i class="living" aria-hidden="true"></i>{text.living}</span><span><i class="dead" aria-hidden="true"></i>{population === 'land' ? text.killed : text.caughtSlaughtered}</span></div>
    <span class="unit">{population === 'land' ? text.oneDotAnimal : text.oneDotFish}</span>
    {#if reduced}<span class="static-label">{text.staticView}</span>{:else}<button class="pause" type="button" aria-pressed={paused} onclick={togglePause}>
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">{#if paused}<path d="m9 6 9 6-9 6Z" />{:else}<path d="M9 6v12M15 6v12" />{/if}</svg>{paused ? text.resume : text.pause}
    </button>{/if}
    <a class="map-link" href={mapHref}>{text.openMap}<span aria-hidden="true">↗</span></a>
  </div>
  <p class="annual">{population === 'land' ? text.landAnnual : text.fishFlowCaption}</p>
  <div class="comparisons">
    <div class="comparison"><p class="comparison-number">{population === 'land' ? text.humanLandValue : text.humanFishValue}</p><div><p>{population === 'land' ? text.humanLandText : text.humanFishText}</p><small>{text.humanBenchmark}</small></div></div>
    {#if population === 'land'}<div class="comparison"><p class="comparison-number">{text.oneSecondValue}</p><div><p>{text.oneSecondText}</p></div></div>{/if}
    <div class="water-comparison"><p class="comparison-condition">{text.dripCondition}</p><div class="comparison"><p class="comparison-number">{population === 'land' ? text.waterLandValue : text.waterFishValue}</p><div><p>{population === 'land' ? text.waterLandText : text.waterFishText}</p><small>{text.dripCaption}</small></div></div>
      <div class="pool-scale" aria-hidden="true">{#each Array(upperPools) as _, index}<span class:uncertain={index >= lowerPools}></span>{/each}</div>
    </div>
  </div>
  <details class="methods"><summary>{text.sources}<span aria-hidden="true">+</span></summary>
    <div><p>{text.previewEdition}</p><p>{text.landMethod}</p><p>{text.fishMethod}</p><p>{text.fishScope}</p><p>{text.motionMethod}</p><p>{text.humanMethod}</p><p>{text.comparisonMethod}</p>
      <ul><li><a href="https://www.fao.org/faostat/en/#data/QCL" target="_blank" rel="noreferrer">{text.faostat} ↗</a></li><li><a href="https://doi.org/10.1017/awf.2024.7" target="_blank" rel="noreferrer">{text.wildPaper} ↗</a></li><li><a href="https://www.cambridge.org/core/journals/animal-welfare/article/estimating-global-numbers-of-farmed-fishes-killed-for-food-annually-from-1990-to-2019/765A7CCA23ADA0249EF37CFC5014D351" target="_blank" rel="noreferrer">{text.farmedPaper} ↗</a></li><li><a href="https://www.un.org/development/desa/pd/sites/www.un.org.development.desa.pd/files/wpp2024_summary_of_results_final_web.pdf" target="_blank" rel="noreferrer">{text.populationSource} ↗</a></li><li><a href="https://www.usgs.gov/water-science-school/science/water-qa-does-a-little-leak-my-house-really-waste-water" target="_blank" rel="noreferrer">{text.dripSource} ↗</a></li><li><a href="https://resources.fina.org/fina/document/2026/02/18/e6815ecc-06d9-4f0b-98e9-4c441cf5e6a3/2026-02-18_World-Aquatics_CR-Final.pdf" target="_blank" rel="noreferrer">{text.poolSource} ↗</a></li><li><a href="https://www.census.gov/library/stories/2024/12/new-year-population.html" target="_blank" rel="noreferrer">{text.humanSource} ↗</a></li></ul>
    </div>
  </details>
</section>

<style>
  .scale-story{--story-bg:#141414;--story-ink:#f2f0e8;--story-muted:#b1b0aa;--story-line:#393936;background:var(--story-bg);color:var(--story-ink);padding:76px 48px 48px;outline:none;scroll-margin-top:24px;font:14px/1.5 system-ui,sans-serif}
  :global(:root[data-theme="light"]) .scale-story{--story-bg:#f2f0e8;--story-ink:#141414;--story-muted:#5c5d57;--story-line:#c7c7bf}
  h2,h3,p{margin:0}h2{font:500 clamp(39px,5.5vw,72px)/1.02 system-ui,sans-serif;letter-spacing:-.055em}h3{font:500 clamp(30px,4vw,54px)/1.05 system-ui,sans-serif;letter-spacing:-.045em}
  button,a{font:inherit;color:inherit}button{cursor:pointer}button:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid #d74749;outline-offset:4px}button{border-radius:0}a{text-decoration:none}a:hover{text-decoration:underline;text-underline-offset:5px}
  .story-intro{margin-bottom:65px}.one-animal{min-height:255px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:13px;border-bottom:1px solid var(--story-line)}.one-dot{width:18px;height:18px;margin:20px 0 9px;border-radius:50%;background:var(--story-ink);transition:background .4s}.one-dot.dead{background:#d74749}.one-animal>span:not(.one-dot){font-size:15px}.one-animal small{font-size:12px;color:var(--story-muted)}
  .story-heading{display:flex;justify-content:space-between;align-items:end;gap:24px;margin-bottom:34px}.segmented{display:inline-flex;border:1px solid var(--story-line);flex-shrink:0}.segmented button{min-height:44px;padding:10px 18px;border:0;background:none;font-size:13px}.segmented button+button{border-left:1px solid var(--story-line)}.segmented button[aria-pressed=true]{color:var(--story-bg);background:var(--story-ink)}.segmented button:hover:not([aria-pressed=true]){background:#8882}
  .rate-row{display:flex;align-items:end;justify-content:space-between;gap:20px;border-top:1px solid var(--story-line);padding-top:26px;margin-bottom:26px}.rate{font:400 clamp(54px,7.5vw,104px)/.95 Georgia,serif;letter-spacing:-.06em;font-variant-numeric:tabular-nums}.rate span{display:inline-block;font:13px/1.4 system-ui,sans-serif;letter-spacing:0;margin-left:16px}.rate-date{font-size:12px;color:var(--story-muted);margin-top:15px}.mode{margin-bottom:2px}.canvas-wrap{height:570px;background:#141414;overflow:hidden;position:relative}canvas{width:100%;height:100%;display:block}.story-controls{display:flex;align-items:center;flex-wrap:wrap;gap:8px 25px;border-bottom:1px solid var(--story-line);padding:11px 0}.legend{display:flex;gap:20px;align-items:center;min-height:44px;font-size:12px}.legend>span{display:flex;align-items:center;gap:8px}.legend i{width:6px;height:6px;border-radius:50%;display:block}.living{background:#f2f0e8;box-shadow:0 0 0 1px #777}.dead{background:#d74749}.unit,.static-label{font-size:12px;color:var(--story-muted)}.pause{margin-left:auto;min-height:44px;display:flex;align-items:center;gap:8px;padding:0 9px;background:none;border:0;font-size:12px}.pause svg{width:14px;height:14px}.map-link{display:inline-flex;gap:25px;align-items:center;min-height:44px;font-size:12px;border-bottom:1px solid var(--story-muted)}.annual{font:400 clamp(19px,2.7vw,34px)/1.3 Georgia,serif;letter-spacing:-.025em;margin:28px 0 25px;max-width:800px}.methods{border-top:1px solid var(--story-line)}summary{list-style:none;cursor:pointer;min-height:55px;display:flex;justify-content:space-between;align-items:center;font-size:12px}summary::-webkit-details-marker{display:none}summary>span{font-size:21px;color:var(--story-muted)}.methods>div{max-width:820px;padding:5px 0 16px;font-size:12px;color:var(--story-muted)}.methods p+p{margin-top:15px}.methods ul{padding-left:17px;line-height:1.7}.methods a{display:inline-flex;align-items:center;min-height:44px;color:var(--story-ink)}
  .comparisons{margin:55px 0 35px}.comparison{display:grid;grid-template-columns:1.1fr 1fr;gap:35px;align-items:center;padding:29px 0;border-top:1px solid var(--story-line)}.comparison-number{font:400 clamp(29px,4vw,56px)/1.1 Georgia,serif;letter-spacing:-.04em}.comparison>div>p{font-size:17px;max-width:30ch;line-height:1.45}.comparison small{display:block;font-size:12px;color:var(--story-muted);line-height:1.6;margin-top:13px}.comparison-condition{font-size:16px;padding:31px 0 0;border-top:1px solid var(--story-line)}.water-comparison .comparison{border:0;padding-top:20px}.pool-scale{display:flex;flex-wrap:wrap;gap:6px;padding:0 0 20px}.pool-scale>span{display:block;width:26px;height:12px;border:1px solid var(--story-ink);background:var(--story-ink)}.pool-scale>span.uncertain{background:transparent;border-style:dashed;opacity:.65}
  .lane-labels{display:grid;grid-template-columns:20% 1fr;gap:18px;padding:0 0 20px}.lane-labels>div{display:flex;flex-direction:column;gap:7px;min-width:0}.lane-labels strong{font-size:13px;font-weight:500}.lane-labels span{font:400 21px/1.1 Georgia,serif}
  .human-context{font-size:12px;color:var(--story-muted);line-height:1.6;margin:-5px 0 19px;max-width:70ch}
  @media(max-width:700px){.scale-story{padding:47px 24px 26px}.story-intro{margin-bottom:43px}.one-animal{min-height:230px}.story-heading{display:block;margin-bottom:25px}.story-heading .segmented{margin-top:24px}.rate-row{display:block;padding-top:25px}.rate{font-size:clamp(37px,10.7vw,69px)}.rate span{display:block;margin:11px 0 0;font-size:12px}.rate-date{line-height:1.6;max-width:32ch}.mode{margin-top:20px}.segmented button{padding:10px 16px}.canvas-wrap{height:500px}.canvas-wrap[data-mode="grid"][data-population="fish"]{height:650px}.story-controls{gap:4px 17px}.legend{width:100%;gap:18px}.unit{margin-right:auto}.pause{margin-left:0}.map-link{gap:12px}.annual{font-size:25px;margin-top:25px}.static-label{min-height:44px;display:flex;align-items:center}.comparisons{margin-top:40px}.comparison{grid-template-columns:minmax(0,1fr);gap:20px;padding:26px 0}.comparison-number{font-size:36px}.comparison>div>p{font-size:16px;max-width:29ch}.pool-scale{gap:5px}.pool-scale>span{width:20px;height:10px}}
  @media(prefers-reduced-motion:reduce){.one-dot{transition:none}}
</style>
