<script lang="ts">
  import { language } from '../language';
  import { storyMessages } from './messages';
  import ThroughputCanvas from './ThroughputCanvas.svelte';
  import MortalityComparison from './MortalityComparison.svelte';
  import { LAND_ANIMALS_2024, poolsForIndividuals } from './comparisons';
  let { mapHref = '#/map' }: { mapHref?: string } = $props();
  const text = $derived(storyMessages($language));
  const pools = Math.round(poolsForIndividuals(LAND_ANIMALS_2024));
</script>

<section class="scale-story" id="landing-scale-story" aria-labelledby="scale-story-title" tabindex="-1">
  <header class="story-intro">
    <h2 id="scale-story-title">{text.introTitle}</h2>
    <p>{text.introExplanation}</p>
    <div class="introductions">
      <figure><svg viewBox="0 0 40 58" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="20" cy="8" r="5" fill="currentColor" stroke="none" /><path d="M20 16v20M9 23h22M12 53l8-17 8 17" /></svg><figcaption>{text.oneHuman}</figcaption></figure>
      <figure><span class="intro-dot" aria-hidden="true"></span><figcaption>{text.oneAnimal}</figcaption></figure>
    </div>
  </header>
  <section class="story-chapter line-chapter" aria-labelledby="line-chapter-title">
    <h3 id="line-chapter-title">{text.humansSentence}</h3>
    <p class="continuation">{text.chickenSentence}</p>
    <MortalityComparison {mapHref} />
  </section>
  <section class="story-chapter land-chapter" aria-labelledby="land-chapter-title">
    <h3 id="land-chapter-title">{text.landSentence}</h3>
    <p class="continuation">{text.landContinuation}</p>
    <ThroughputCanvas population="land" {mapHref} />
    <p class="annual">{text.landAnnual}</p>
  </section>
  <section class="story-chapter fish-chapter" aria-labelledby="fish-chapter-title">
    <h3 id="fish-chapter-title">{text.fishSentence}</h3>
    <p class="continuation">{text.fishContinuation}</p>
    <ThroughputCanvas population="fish" {mapHref} />
  </section>
  <div class="comparisons">
    <div class="comparison"><p class="comparison-number">{text.humanLandValue}</p><div><p>{text.humanLandText}</p><small>{text.humanBenchmark}</small></div></div>
    <div class="comparison"><p class="comparison-number">{text.oneSecondValue}</p><div><p>{text.oneSecondText}</p></div></div>
    <div class="water-comparison"><p class="comparison-condition">{text.dripCondition}</p><div class="comparison"><p class="comparison-number">{text.waterLandValue}</p><div><p>{text.waterLandText}</p><small>{text.dripCaption}</small></div></div>
      <div class="pool-scale" aria-hidden="true">{#each Array(pools) as _}<span></span>{/each}</div>
    </div>
  </div>
  <details class="methods"><summary>{text.sources}<span aria-hidden="true">+</span></summary>
    <div><p>{text.previewEdition}</p><p>{text.humanMethod}</p><p>{text.chickenMethod}</p><p>{text.landMethod}</p><p>{text.fishMethod}</p><p>{text.fishScope}</p><p>{text.motionMethod}</p><p>{text.comparisonMethod}</p>
      <ul>
        <li><a href="https://www.census.gov/library/stories/2024/12/new-year-population.html" target="_blank" rel="noreferrer">{text.humanSource} ↗</a></li>
        <li><a href="https://foodprint.org/blog/line-speeds/" target="_blank" rel="noreferrer">{text.foodprintSource} ↗</a></li>
        <li><a href="https://public-inspection.federalregister.gov/2026-03227.pdf" target="_blank" rel="noreferrer">{text.usdaSource} ↗</a></li>
        <li><a href="https://www.fao.org/faostat/en/#data/QCL" target="_blank" rel="noreferrer">{text.faostat} ↗</a></li>
        <li><a href="https://doi.org/10.1017/awf.2024.7" target="_blank" rel="noreferrer">{text.wildPaper} ↗</a></li>
        <li><a href="https://www.cambridge.org/core/journals/animal-welfare/article/estimating-global-numbers-of-farmed-fishes-killed-for-food-annually-from-1990-to-2019/765A7CCA23ADA0249EF37CFC5014D351" target="_blank" rel="noreferrer">{text.farmedPaper} ↗</a></li>
        <li><a href="https://www.un.org/development/desa/pd/sites/www.un.org.development.desa.pd/files/wpp2024_summary_of_results_final_web.pdf" target="_blank" rel="noreferrer">{text.populationSource} ↗</a></li>
        <li><a href="https://www.usgs.gov/water-science-school/science/water-qa-does-a-little-leak-my-house-really-waste-water" target="_blank" rel="noreferrer">{text.dripSource} ↗</a></li>
        <li><a href="https://resources.fina.org/fina/document/2026/02/18/e6815ecc-06d9-4f0b-98e9-4c441cf5e6a3/2026-02-18_World-Aquatics_CR-Final.pdf" target="_blank" rel="noreferrer">{text.poolSource} ↗</a></li>
      </ul>
    </div>
  </details>
</section>

<style>
  .scale-story{--story-bg:#141414;--story-ink:#f2f0e8;--story-muted:#b1b0aa;--story-line:#393936;background:var(--story-bg);color:var(--story-ink);padding:77px 48px 42px;outline:none;scroll-margin-top:24px;font:14px/1.5 system-ui,sans-serif}
  :global(:root[data-theme="light"]) .scale-story{--story-bg:#f2f0e8;--story-ink:#141414;--story-muted:#5c5d57;--story-line:#c7c7bf}
  h2,h3,p{margin:0}h2,h3{font:500 clamp(35px,4.6vw,66px)/1.07 system-ui,sans-serif;letter-spacing:-.05em;max-width:1050px}.story-intro>p,.continuation{font-size:20px;line-height:1.5;color:var(--story-muted);margin-top:23px;max-width:55ch}.story-intro>p{font-size:17px}.introductions{display:grid;grid-template-columns:1fr 1fr;gap:60px;min-height:240px;align-items:center;background:#141414;color:#f2f0e8;margin-top:32px;border-bottom:1px solid var(--story-line)}figure{margin:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:25px;min-height:210px}figure svg{width:28px;height:43px}.intro-dot{width:18px;height:18px;margin:12px 0 13px;background:#f2f0e8;border-radius:50%}figcaption{font-size:14px}.story-chapter{margin-top:86px}.continuation{max-width:49ch}.annual{font:400 clamp(21px,2.7vw,36px)/1.3 Georgia,serif;letter-spacing:-.025em;margin-top:28px;max-width:850px}
  .comparisons{margin:72px 0 32px}.comparison{display:grid;grid-template-columns:1.1fr 1fr;gap:35px;align-items:center;padding:29px 0;border-top:1px solid var(--story-line)}.comparison-number{font:400 clamp(29px,4vw,56px)/1.1 Georgia,serif;letter-spacing:-.04em}.comparison>div>p{font-size:17px;max-width:30ch;line-height:1.45}.comparison small{display:block;font-size:12px;color:var(--story-muted);line-height:1.6;margin-top:13px}.comparison-condition{font-size:16px;padding:31px 0 0;border-top:1px solid var(--story-line)}.water-comparison .comparison{border:0;padding-top:20px}.pool-scale{display:flex;flex-wrap:wrap;gap:6px;padding:0 0 20px}.pool-scale>span{display:block;width:26px;height:12px;border:1px solid var(--story-ink);background:var(--story-ink)}
  .methods{border-top:1px solid var(--story-line)}summary{list-style:none;cursor:pointer;min-height:55px;display:flex;justify-content:space-between;align-items:center;font-size:12px}summary::-webkit-details-marker{display:none}summary>span{font-size:21px;color:var(--story-muted)}.methods>div{max-width:820px;padding:5px 0 16px;font-size:12px;color:var(--story-muted)}.methods p+p{margin-top:15px}.methods ul{padding-left:17px;line-height:1.7}.methods a{display:inline-flex;align-items:center;min-height:44px;color:var(--story-ink);text-underline-offset:4px}summary:focus-visible,a:focus-visible{outline:2px solid #d74749;outline-offset:4px}
  @media(max-width:700px){.scale-story{padding:47px 24px 26px}h2,h3{font-size:clamp(31px,8.3vw,47px)}.story-intro>p{font-size:15px;max-width:30ch}.introductions{gap:22px;min-height:220px;margin-top:28px}figure{min-height:210px}figcaption{font-size:13px}.story-chapter{margin-top:62px}.continuation{font-size:17px;margin-top:20px;max-width:29ch}.annual{font-size:25px}.comparisons{margin-top:55px}.comparison{grid-template-columns:minmax(0,1fr);gap:20px;padding:26px 0}.comparison-number{font-size:36px}.comparison>div>p{font-size:16px;max-width:29ch}.pool-scale{gap:5px}.pool-scale>span{width:20px;height:10px}}
</style>
