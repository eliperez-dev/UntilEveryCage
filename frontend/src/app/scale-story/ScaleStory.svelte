<script lang="ts">
  import { language } from '../language';
  import { storyMessages } from './messages';
  import ThroughputCanvas from './ThroughputCanvas.svelte';
  import MortalityComparison from './MortalityComparison.svelte';
  import { LAND_ANIMALS_2024, poolsForIndividuals } from './comparisons';
  let { mapHref = '#/map' }: { mapHref?: string } = $props();
  const text = $derived(storyMessages($language));
  const humanStatement = $derived(text.humanLandText.split('{emphasis}'));
  const timeStatement = $derived(text.oneSecondText.split('{emphasis}'));
  const waterStatement = $derived(text.dripCondition.split('{emphasis}'));
  const pools = Math.round(poolsForIndividuals(LAND_ANIMALS_2024));
</script>

<section class="scale-story" id="landing-scale-story" aria-label={text.introTitle} tabindex="-1">
  <section class="line-chapter" aria-labelledby="line-claim-title">
    <h3 id="line-claim-title">{text.lineClaim}</h3>
    <MortalityComparison {mapHref} />
  </section>
  <section class="story-chapter land-chapter" aria-labelledby="land-chapter-title">
    <h3 id="land-chapter-title">{text.landSentence}</h3>
    <ThroughputCanvas population="land" {mapHref} />
    <p class="annual">{text.landAnnual}</p>
    <div class="comparisons">
      <div class="comparison"><p class="comparison-statement">{humanStatement[0]}<strong class="comparison-emphasis">{text.humanLandValue}</strong>{humanStatement[1]}</p><small>{text.humanBenchmark}</small></div>
    </div>
  </section>
  <section class="story-chapter fish-chapter" aria-labelledby="fish-chapter-title">
    <h3 id="fish-chapter-title">{text.fishSentence}</h3>
    <ThroughputCanvas population="fish" {mapHref} />
  </section>
  <details class="methods"><summary>{text.sources}<span aria-hidden="true">+</span></summary>
    <div>
      <div class="secondary-comparisons">
        <div class="comparison"><p class="comparison-statement">{timeStatement[0]}<strong class="comparison-emphasis">{text.oneSecondValue}</strong>{timeStatement[1]}</p></div>
        <div class="water-comparison"><div class="comparison"><p class="comparison-statement">{waterStatement[0]}<strong class="comparison-emphasis">{text.waterLandValue}</strong>{waterStatement[1]}</p><div class="comparison-details"><p>{text.waterLandText}</p><small>{text.dripCaption}</small></div></div>
          <div class="pool-scale" aria-hidden="true">{#each Array(pools) as _}<span></span>{/each}</div>
        </div>
      </div>
      <p>{text.previewEdition}</p><p>{text.humanMethod}</p><p>{text.chickenMethod}</p><p>{text.landMethod}</p><p>{text.fishMethod}</p><p>{text.fishScope}</p><p>{text.motionMethod}</p><p>{text.comparisonMethod}</p>
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
  .scale-story{--story-bg:#141414;--story-ink:#f2f0e8;--story-muted:#b1b0aa;--story-line:#393936;background:var(--story-bg);color:var(--story-ink);padding:32px max(48px,calc((100% - 1100px)/2)) 24px;outline:none;scroll-margin-top:24px;font:14px/1.5 system-ui,sans-serif}
  :global(:root[data-theme="light"]) .scale-story{--story-bg:#f2f0e8;--story-ink:#141414;--story-muted:#5c5d57;--story-line:#c7c7bf}
  h3,p{margin:0}h3{font:400 29px/1.25 Georgia,serif;letter-spacing:-.025em;max-width:1050px}.line-chapter>h3{margin-bottom:20px}.story-chapter{margin-top:48px}.annual{font:400 clamp(21px,2.7vw,36px)/1.3 Georgia,serif;letter-spacing:-.025em;margin-top:18px;max-width:850px}
  .comparisons{margin:18px 0 0}.comparison{padding:20px 0;border-top:1px solid var(--story-line)}.comparison-statement{font-size:22px;line-height:1.5;max-width:66ch}.comparison-emphasis{font-size:inherit;font-weight:700;text-transform:none}.comparison-details{margin-top:8px}.comparison-details>p{font-size:15px;max-width:55ch;line-height:1.5}.comparison small{display:block;font-size:12px;color:var(--story-muted);line-height:1.6;margin-top:8px}.pool-scale{display:flex;flex-wrap:wrap;gap:6px;padding:0 0 12px}.pool-scale>span{display:block;width:26px;height:12px;border:1px solid var(--story-ink);background:var(--story-ink)}
  .methods{border-top:1px solid var(--story-line);margin-top:16px}summary{list-style:none;cursor:pointer;min-height:48px;display:flex;justify-content:space-between;align-items:center;font-size:12px}summary::-webkit-details-marker{display:none}summary>span{font-size:21px;color:var(--story-muted)}.methods>div{max-width:820px;padding:5px 0 12px;font-size:12px;color:var(--story-muted)}.methods .comparison{padding:16px 0}.methods .comparison-statement{font-size:18px;color:var(--story-ink)}.methods p+p{margin-top:10px}.methods ul{padding-left:17px;line-height:1.7}.methods a{display:inline-flex;align-items:center;min-height:44px;color:var(--story-ink);text-underline-offset:4px}summary:focus-visible,a:focus-visible{outline:2px solid #d74749;outline-offset:4px}
  @media(max-width:700px){.scale-story{padding:28px 20px 20px}h3{font-size:26px}.story-chapter{margin-top:34px}.annual{font-size:25px}.comparison{padding:18px 0}.comparison-statement{font-size:19px}.comparison-details>p{font-size:15px}.pool-scale{gap:5px}.pool-scale>span{width:20px;height:10px}}
</style>
