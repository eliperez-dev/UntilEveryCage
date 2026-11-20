<script lang="ts">
  import { language } from '../language';
  import { documentElapsedMilliseconds, estimateSinceDocumentOpen } from '../../features/counter/documentElapsed';
  import { storyMessages } from './messages';
  import type { StoryPopulation } from './engine';

  let { population, rate, label, range }: {
    population: StoryPopulation | 'human' | 'chicken';
    rate: number;
    label: string;
    range?: readonly [number, number] | undefined;
  } = $props();
  const text = $derived(storyMessages($language));
  const format = $derived(new Intl.NumberFormat($language, { maximumFractionDigits: 0 }));
  const total = $derived(estimateSinceDocumentOpen(rate, $documentElapsedMilliseconds));
  const displayRate = $derived(range ? range.map(value => format.format(value)).join('–') : format.format(rate));
</script>

<div class="story-counter">
  <strong class="story-total" data-counter={population} data-total={total}>{format.format(total)}</strong>
  <p class="story-label">{label}</p>
  <p class="story-rate">{text.aboutPerSecond.replace('{rate}', displayRate)}</p>
</div>

<style>
  .story-total {
    display: block;
    font-size: clamp(30px, 5vw, 56px);
    font-weight: 700;
    line-height: 1.1;
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
  }
  .story-label { margin: 6px 0 0; font-size: 16px; line-height: 1.4; }
  .story-rate { margin: 4px 0 0; color: var(--story-muted); font-size: 14px; line-height: 1.4; }
</style>
