<script lang="ts">
  import { onMount } from 'svelte';
  import { language } from '../language';
  import { storyMessages } from './messages';
  import { documentElapsedMilliseconds, estimateSinceDocumentOpen } from '../../features/counter/documentElapsed';
  import { ActiveStoryClock, CHICKEN_LINE_RATE, lineParticles } from './engine';
  let { mapHref }: { mapHref: string } = $props();
  const text = $derived(storyMessages($language));
  const counterFormat = $derived(new Intl.NumberFormat($language, { maximumFractionDigits: 0 }));
  const humanTotal = $derived(estimateSinceDocumentOpen(2, $documentElapsedMilliseconds));
  const chickenTotal = $derived(estimateSinceDocumentOpen(CHICKEN_LINE_RATE, $documentElapsedMilliseconds));
  let reduced = $state(true), canvas: HTMLCanvasElement;
  onMount(() => {
    const ctx = canvas.getContext('2d'); if (!ctx) return;
    const clock = new ActiveStoryClock(), preference = matchMedia('(prefers-reduced-motion: reduce)');
    let width = 1, height = 1, visible = false, frame = 0, disposed = false, lastDiagnostic = 0;
    function dot(x: number, y: number, dead: boolean, outcome: string) {
      ctx!.fillStyle = dead ? outcome : '#f2f0e8';
      ctx!.beginPath(); ctx!.arc(x, y, 3, 0, Math.PI * 2); ctx!.fill();
    }
    function render() {
      if (disposed) return;
      ctx!.clearRect(0, 0, width, height);
      const gap = width < 500 ? 22 : 60, lane = (width - gap) / 2, seconds = reduced ? 1.68 : clock.elapsed;
      ctx!.lineWidth = 1; ctx!.strokeStyle = '#919392'; ctx!.beginPath(); ctx!.moveTo(0, height * .48); ctx!.lineTo(lane, height * .48); ctx!.stroke();
      ctx!.strokeStyle = '#d74749'; ctx!.beginPath(); ctx!.moveTo(lane + gap, height * .48); ctx!.lineTo(width, height * .48); ctx!.stroke();
      lineParticles(seconds, 2, lane, height, (_id, x, y, dead) => dot(x, y, dead, '#919392'));
      lineParticles(seconds, CHICKEN_LINE_RATE, lane, height, (_id, x, y, dead) => dot(x + lane + gap, y, dead, '#d74749'));
    }
    function resize() {
      const rect = canvas.getBoundingClientRect(), ratio = Math.min(2, devicePixelRatio || 1);
      width = Math.max(1, rect.width); height = Math.max(1, rect.height); canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      ctx!.setTransform(ratio, 0, 0, ratio, 0, 0); render();
    }
    const shouldRun = () => !disposed && visible && !reduced && !document.hidden;
    function publish() { canvas.dataset.emitted = String(clock.emitted(CHICKEN_LINE_RATE)); canvas.dataset.humanEmitted = String(clock.emitted(2)); }
    function tick(now: number) { frame = 0; if (!shouldRun()) return; clock.advance(now); render(); if (now - lastDiagnostic > 250) { publish(); lastDiagnostic = now; } if (shouldRun()) frame = requestAnimationFrame(tick); }
    function sync() { clock.setRunning(shouldRun(), performance.now()); publish(); canvas.dataset.state = reduced ? 'static' : shouldRun() ? 'running' : 'offscreen'; if (shouldRun()) { if (!frame) frame = requestAnimationFrame(tick); } else { cancelAnimationFrame(frame); frame = 0; } }
    function preferenceChanged() { reduced = preference.matches; sync(); render(); }
    const observer = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? false; sync(); });
    const resizeObserver = new ResizeObserver(resize); observer.observe(canvas); resizeObserver.observe(canvas);
    preference.addEventListener('change', preferenceChanged); document.addEventListener('visibilitychange', sync); preferenceChanged(); resize();
    return () => { disposed = true; cancelAnimationFrame(frame); observer.disconnect(); resizeObserver.disconnect(); preference.removeEventListener('change', preferenceChanged); document.removeEventListener('visibilitychange', sync); clock.setRunning(false, performance.now()); canvas.width = 1; canvas.height = 1; };
  });
</script>

<div class="mortality-comparison">
  <div class="lane-headings"><div><strong>{text.humans}</strong><span class="lane-rate">2<small>{text.deathsPerSecond}</small><span class="since-open" data-counter="human" data-total={humanTotal}>≈ {counterFormat.format(humanTotal)} {text.sinceOpened}</span></span><p class="lane-caption">{text.humanDate}</p></div><div><strong>{text.chickens}</strong><span class="lane-rate">≈ {CHICKEN_LINE_RATE.toLocaleString($language, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}<small>{text.chickensPerSecond}</small><span class="since-open" data-counter="chicken" data-total={chickenTotal}>≈ {counterFormat.format(chickenTotal)} {text.sinceOpened}</span></span><p class="lane-caption">{text.chickenRate}<br />{text.chickenDate}</p></div></div>
  <p class="unit">{text.introExplanation}</p>
  <div class="line-labels"><strong>{text.humanStreamTitle}</strong><strong>{text.chickenStreamTitle}</strong></div>
  <div class="line-field" role="img" aria-label={text.lineCanvas}><canvas bind:this={canvas} aria-hidden="true"></canvas></div>
  <div class="controls">{#if reduced}<span>{text.staticView}</span>{/if}<a class="map-link" href={mapHref}>{text.openMap}<span aria-hidden="true">↗</span></a></div>
</div>

<style>
  .mortality-comparison{--line-label-red:#e87c7d}
  :global(:root[data-theme="light"]) .mortality-comparison{--line-label-red:#a92a30}
  .since-open{font:12px/1.5 system-ui,sans-serif;letter-spacing:0;color:var(--story-muted);font-variant-numeric:tabular-nums;max-width:100%}
  .mortality-comparison{margin-top:0}.lane-headings{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);grid-template-rows:auto auto auto;column-gap:60px;row-gap:0}.lane-headings>div{display:grid;grid-template-rows:subgrid;grid-row:span 3;align-items:start;justify-items:start;padding-top:14px;min-width:0}.lane-headings strong{overflow-wrap:anywhere;hyphens:auto;font-size:18px;font-weight:500;line-height:1.4}.lane-rate{display:flex;flex-direction:column;align-items:flex-start;gap:6px;font:400 36px/1.2 Georgia,serif;letter-spacing:-.025em;padding-top:10px;max-width:100%}.lane-rate small{font:19px/1.4 system-ui,sans-serif;letter-spacing:0;max-width:100%}.lane-caption{font-size:12px;line-height:1.7;color:var(--story-muted);margin:10px 0 0}.unit{font-size:12px;line-height:1.5;color:var(--story-muted);margin:18px 0 8px}.line-field{height:220px;margin-top:8px;background:#141414}canvas{display:block;width:100%;height:100%}.line-labels{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:60px;font-size:14px;line-height:1.45;align-items:end}.line-labels>strong{overflow-wrap:anywhere;hyphens:auto;font-weight:400;color:var(--story-muted)}.line-labels>strong+strong{color:var(--line-label-red)}.controls{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:22px;padding:6px 0;font-size:12px}.controls>span{margin-right:auto;color:var(--story-muted)}a{font:inherit;color:inherit;min-height:44px}.map-link{display:flex;align-items:center;gap:22px;text-decoration:none;border-bottom:1px solid var(--story-muted)}a:focus-visible{outline:2px solid #d74749;outline-offset:4px}
  @media(max-width:700px){.lane-headings,.line-labels{column-gap:22px}.lane-headings strong{font-size:16px;line-height:1.4}.lane-rate{font-size:30px;padding-top:10px}.lane-rate small{font-size:16px}.lane-caption{font-size:11px;line-height:1.6}.unit{font-size:11px}.line-field{height:200px}.line-labels{font-size:12px}.controls{gap:18px}}
</style>
