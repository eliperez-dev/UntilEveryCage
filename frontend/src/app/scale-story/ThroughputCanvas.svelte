<script lang="ts">
  import { onMount } from 'svelte';
  import { language } from '../language';
  import { storyMessages } from './messages';
  import { ActiveStoryClock, funnelLayout, funnelParticles, STORY_RATES, type FunnelLayout, type StoryPopulation } from './engine';
  let { population, mapHref }: { population: StoryPopulation; mapHref: string } = $props();
  const text = $derived(storyMessages($language));
  let reduced = $state(true);
  let canvas: HTMLCanvasElement;

  onMount(() => {
    const context = canvas.getContext('2d'); if (!context) return;
    const clock = new ActiveStoryClock(), preference = matchMedia('(prefers-reduced-motion: reduce)');
    const whites = new Float32Array(320000), reds = new Float32Array(320000);
    let whiteCount = 0, redCount = 0, width = 1, height = 1, ratio = 1, visible = false;
    let frame = 0, disposed = false, lastDiagnostic = 0;
    let pixelImage: ImageData | null = null, pixels: Uint32Array | null = null;
    let layout: FunnelLayout = funnelLayout(STORY_RATES[population], width, height);
    const visit = (_id: number, x: number, y: number, dead: boolean) => {
      const buffer = dead ? reds : whites, index = dead ? redCount++ : whiteCount++;
      buffer[index * 2] = x; buffer[index * 2 + 1] = y;
    };
    function circles(points: Float32Array, count: number, color: string) {
      context!.fillStyle = color; context!.beginPath();
      const radius = width < 500 ? 1.1 : 1.55;
      for (let i = 0; i < count; i++) { const x = points[i * 2]!, y = points[i * 2 + 1]!; context!.moveTo(x + radius, y); context!.arc(x, y, radius, 0, Math.PI * 2); }
      context!.fill();
    }
    function pixelDots(points: Float32Array, count: number, color: number) {
      const pixelWidth = canvas.width, pixelHeight = canvas.height, size = ratio > 1 ? 2 : 1;
      for (let i = 0; i < count; i++) {
        const x = Math.round(points[i * 2]! * ratio), y = Math.round(points[i * 2 + 1]! * ratio);
        if (x < 0 || y < 0 || x + size > pixelWidth || y + size > pixelHeight) continue;
        const index = y * pixelWidth + x; pixels![index] = color;
        if (size === 2) { pixels![index + 1] = color; pixels![index + pixelWidth] = color; pixels![index + pixelWidth + 1] = color; }
      }
    }
    function render() {
      if (disposed) return;
      context!.clearRect(0, 0, width, height); whiteCount = 0; redCount = 0;
      const seconds = reduced ? 1.68 : clock.elapsed;
      funnelParticles(seconds, STORY_RATES[population], width, height, visit, layout);
      if (population === 'fish' && pixelImage && pixels) {
        pixels.fill(0); pixelDots(whites, whiteCount, 0xffe8f0f2); pixelDots(reds, redCount, 0xff4947d7); context!.putImageData(pixelImage, 0, 0);
      } else { circles(whites, whiteCount, '#f2f0e8'); circles(reds, redCount, '#d74749'); }
      {
        const center = width / 2, distance = layout.throat - layout.front;
        const guideHalfWidth = layout.columns > 1 ? Math.min((layout.right - layout.left) / 2, layout.throatHalfWidth + 8) : 0;
        context!.strokeStyle = '#f2f0e82e'; context!.lineWidth = .75; context!.beginPath();
        for (const side of [-1, 1]) {
          const edge = side < 0 ? layout.left - 10 : layout.right + 10;
          context!.moveTo(edge, layout.front + 5);
          context!.bezierCurveTo(edge, layout.front + distance * .32,
            center + side * guideHalfWidth, layout.throat - distance * .42, center + side * guideHalfWidth, layout.throat + 8);
        }
        context!.stroke();
      }
    }
    function resize() {
      const rect = canvas.getBoundingClientRect(); width = Math.max(1, rect.width); height = Math.max(1, rect.height); ratio = Math.min(2, devicePixelRatio || 1);
      layout = funnelLayout(STORY_RATES[population], width, height);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context!.setTransform(ratio, 0, 0, ratio, 0, 0);
      if (population === 'fish') { pixelImage = context!.createImageData(canvas.width, canvas.height); pixels = new Uint32Array(pixelImage.data.buffer); }
      render();
    }
    const shouldRun = () => !disposed && visible && !reduced && !document.hidden;
    function publish() {
      canvas.dataset.emitted = String(clock.emitted(STORY_RATES[population]));
      canvas.dataset.points = String(whiteCount + redCount);
      canvas.dataset.columns = String(layout.columns);
    }
    function tick(now: number) {
      frame = 0; if (!shouldRun()) return;
      clock.advance(now); render(); if (now - lastDiagnostic > 250) { publish(); lastDiagnostic = now; }
      if (shouldRun()) frame = requestAnimationFrame(tick);
    }
    function sync() {
      clock.setRunning(shouldRun(), performance.now()); publish();
      canvas.dataset.state = reduced ? 'static' : shouldRun() ? 'running' : 'offscreen';
      if (shouldRun()) { if (!frame) frame = requestAnimationFrame(tick); } else { cancelAnimationFrame(frame); frame = 0; }
    }
    function preferenceChanged() { reduced = preference.matches; sync(); render(); }
    const observer = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? false; sync(); });
    const resizeObserver = new ResizeObserver(resize);
    observer.observe(canvas); resizeObserver.observe(canvas); preference.addEventListener('change', preferenceChanged); document.addEventListener('visibilitychange', sync);
    resize(); preferenceChanged();
    return () => { disposed = true; cancelAnimationFrame(frame); observer.disconnect(); resizeObserver.disconnect(); preference.removeEventListener('change', preferenceChanged); document.removeEventListener('visibilitychange', sync); clock.setRunning(false, performance.now()); canvas.width = 1; canvas.height = 1; pixelImage = null; pixels = null; };
  });
</script>

<div class="throughput" data-population={population}>
  <div class="rate-row"><div><p class="rate">{population === 'land' ? '2,779' : '33,500–65,700'}<span>{population === 'land' ? text.animalsPerSecond : text.fishPerSecond}</span></p><p class="date">{population === 'land' ? text.landDate : text.fishDate}</p></div></div>
  {#if population === 'fish'}<p class="flow-caption">{text.fishFlowCaption}</p>{/if}
  <p class="unit">{population === 'land' ? text.oneDotAnimal : text.oneDotFish}</p>
  <div class="canvas-wrap" data-mode="funnel" role="img" aria-label={population === 'land' ? text.landCanvas : text.fishCanvas}><canvas bind:this={canvas} aria-hidden="true"></canvas></div>
  <div class="controls">
    {#if reduced}<span class="static-label">{text.staticView}</span>{/if}
    <a class="map-link" href={mapHref}>{text.openMap}<span aria-hidden="true">↗</span></a>
  </div>
</div>

<style>
  .throughput{margin-top:20px}.rate-row{border-top:1px solid var(--story-line);padding-top:16px}.rate{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 20px;font:400 48px/1.15 Georgia,serif;letter-spacing:-.025em;margin:0}.rate span{font:20px/1.5 system-ui,sans-serif;letter-spacing:0}.date,.flow-caption{font-size:12px;color:var(--story-muted);line-height:1.6;margin:10px 0 14px}.flow-caption{margin-top:-4px}.canvas-wrap{height:500px;background:#141414;overflow:hidden}canvas{display:block;width:100%;height:100%}.controls{display:flex;align-items:center;flex-wrap:wrap;gap:6px 23px;border-bottom:1px solid var(--story-line);padding:6px 0;font-size:12px}.unit{margin:0 0 8px;color:var(--story-muted);font-size:12px;line-height:1.5}a{font:inherit;color:inherit}.map-link{display:inline-flex;align-items:center;gap:22px;min-height:44px;margin-left:auto;border-bottom:1px solid var(--story-muted);text-decoration:none}.map-link:hover{text-decoration:underline}.static-label{color:var(--story-muted)}a:focus-visible{outline:2px solid #d74749;outline-offset:3px}
  @media(max-width:700px){.throughput{margin-top:18px}.rate{font-size:32px;gap:6px 16px}.rate span{font-size:16px;flex-basis:100%}.date{max-width:34ch}.canvas-wrap{height:430px}.controls{gap:3px 15px}.map-link{gap:10px}.static-label{font-size:11px}.controls>.static-label{max-width:110px}}
</style>
