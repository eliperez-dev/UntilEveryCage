<script lang="ts">
  import { onMount } from 'svelte';
  import { language } from '../language';
  import { storyMessages } from './messages';
  import { ActiveStoryClock, funnelParticles, gridParticles, STORY_RATES, type StoryMode, type StoryPopulation } from './engine';
  let { population, mapHref }: { population: StoryPopulation; mapHref: string } = $props();
  const text = $derived(storyMessages($language));
  let mode = $state<StoryMode>('funnel');
  let paused = $state(false), reduced = $state(true);
  let canvas: HTMLCanvasElement;
  let redraw: (() => void) | null = null, syncRuntime: (() => void) | null = null;
  function chooseMode(value: StoryMode) { mode = value; redraw?.(); }
  function togglePause() { paused = !paused; syncRuntime?.(); }

  onMount(() => {
    const context = canvas.getContext('2d'); if (!context) return;
    const clock = new ActiveStoryClock(), preference = matchMedia('(prefers-reduced-motion: reduce)');
    const whites = new Float32Array(320000), reds = new Float32Array(320000);
    let whiteCount = 0, redCount = 0, width = 1, height = 1, ratio = 1, visible = false;
    let frame = 0, disposed = false, lastDiagnostic = 0;
    let pixelImage: ImageData | null = null, pixels: Uint32Array | null = null;
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
      (mode === 'funnel' ? funnelParticles : gridParticles)(reduced ? 1.68 : clock.elapsed, STORY_RATES[population], width, height, visit);
      if (population === 'fish' && pixelImage && pixels) {
        pixels.fill(0); pixelDots(whites, whiteCount, 0xffe8f0f2); pixelDots(reds, redCount, 0xff4947d7); context!.putImageData(pixelImage, 0, 0);
      } else { circles(whites, whiteCount, '#f2f0e8'); circles(reds, redCount, '#d74749'); }
      if (mode === 'funnel') {
        context!.strokeStyle = '#f2f0e84a'; context!.lineWidth = 1; context!.beginPath();
        context!.moveTo(width * .055, 8); context!.bezierCurveTo(width * .11, height * .38, width * .44, height * .36, width * .482, height * .53);
        context!.moveTo(width * .945, 8); context!.bezierCurveTo(width * .89, height * .38, width * .56, height * .36, width * .518, height * .53); context!.stroke();
      }
    }
    function resize() {
      const rect = canvas.getBoundingClientRect(); width = Math.max(1, rect.width); height = Math.max(1, rect.height); ratio = Math.min(2, devicePixelRatio || 1);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context!.setTransform(ratio, 0, 0, ratio, 0, 0); pixelImage = context!.createImageData(canvas.width, canvas.height); pixels = new Uint32Array(pixelImage.data.buffer); render();
    }
    const shouldRun = () => !disposed && visible && !paused && !reduced && !document.hidden;
    function publish() { canvas.dataset.emitted = String(clock.emitted(STORY_RATES[population])); }
    function tick(now: number) {
      frame = 0; if (!shouldRun()) return;
      clock.advance(now); render(); if (now - lastDiagnostic > 250) { publish(); lastDiagnostic = now; }
      if (shouldRun()) frame = requestAnimationFrame(tick);
    }
    function sync() {
      clock.setRunning(shouldRun(), performance.now()); publish();
      canvas.dataset.state = reduced ? 'static' : paused ? 'paused' : shouldRun() ? 'running' : 'offscreen';
      if (shouldRun()) { if (!frame) frame = requestAnimationFrame(tick); } else { cancelAnimationFrame(frame); frame = 0; }
    }
    function preferenceChanged() { reduced = preference.matches; sync(); render(); }
    const observer = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? false; sync(); });
    const resizeObserver = new ResizeObserver(resize);
    observer.observe(canvas); resizeObserver.observe(canvas); preference.addEventListener('change', preferenceChanged); document.addEventListener('visibilitychange', sync);
    redraw = render; syncRuntime = sync; preferenceChanged(); resize();
    return () => { disposed = true; redraw = null; syncRuntime = null; cancelAnimationFrame(frame); observer.disconnect(); resizeObserver.disconnect(); preference.removeEventListener('change', preferenceChanged); document.removeEventListener('visibilitychange', sync); clock.setRunning(false, performance.now()); canvas.width = 1; canvas.height = 1; pixelImage = null; pixels = null; };
  });
</script>

<div class="throughput" data-population={population}>
  <div class="rate-row"><div><p class="rate">{population === 'land' ? '2,779' : '33,500–65,700'}<span>{population === 'land' ? text.animalsPerSecond : text.fishPerSecond}</span></p><p class="date">{population === 'land' ? text.landDate : text.fishDate}</p></div></div>
  {#if population === 'fish'}<p class="flow-caption">{text.fishFlowCaption}</p>{/if}
  <div class="canvas-wrap" data-mode={mode} role="img" aria-label={population === 'land' ? text.landCanvas : text.fishCanvas}><canvas bind:this={canvas} aria-hidden="true"></canvas></div>
  <div class="controls"><span class="unit">{population === 'land' ? text.oneDotAnimal : text.oneDotFish}</span>
    <div class="mode" role="group" aria-label={text.visualization}><button type="button" aria-pressed={mode === 'funnel'} onclick={() => chooseMode('funnel')}>{text.funnel}</button><button type="button" aria-pressed={mode === 'grid'} onclick={() => chooseMode('grid')}>{text.grid}</button></div>
    {#if reduced}<span class="static-label">{text.staticView}</span>{:else}<button class="pause" type="button" aria-pressed={paused} onclick={togglePause}>{paused ? text.resume : text.pause}</button>{/if}
    <a class="map-link" href={mapHref}>{text.openMap}<span aria-hidden="true">↗</span></a>
  </div>
</div>

<style>
  .throughput{margin-top:35px}.rate-row{border-top:1px solid var(--story-line);padding-top:24px}.rate{font:400 clamp(52px,7vw,102px)/.95 Georgia,serif;letter-spacing:-.055em;margin:0}.rate span{display:inline-block;font:13px/1.5 system-ui,sans-serif;letter-spacing:0;margin-left:17px}.date,.flow-caption{font-size:12px;color:var(--story-muted);line-height:1.6;margin:15px 0 23px}.flow-caption{margin-top:-9px}.canvas-wrap{height:570px;background:#141414;overflow:hidden}canvas{display:block;width:100%;height:100%}.controls{display:flex;align-items:center;flex-wrap:wrap;gap:6px 23px;border-bottom:1px solid var(--story-line);padding:10px 0;font-size:12px}.unit{margin-right:auto;color:var(--story-muted)}button,a{font:inherit;color:inherit}button{cursor:pointer;border-radius:0;min-height:44px;background:none}.mode{display:flex}.mode button{border:0;padding:8px 13px;color:var(--story-muted)}.mode button[aria-pressed=true]{color:var(--story-ink);text-decoration:underline;text-underline-offset:6px}.pause{border:0;padding:8px 5px;min-width:60px}.map-link{display:inline-flex;align-items:center;gap:22px;min-height:44px;border-bottom:1px solid var(--story-muted);text-decoration:none}.map-link:hover{text-decoration:underline}.static-label{color:var(--story-muted)}button:focus-visible,a:focus-visible{outline:2px solid #d74749;outline-offset:3px}
  @media(max-width:700px){.throughput{margin-top:28px}.rate{font-size:clamp(37px,10.5vw,64px)}.rate span{display:block;font-size:12px;margin:10px 0 0}.date{max-width:34ch}.canvas-wrap{height:490px}.throughput[data-population="fish"] .canvas-wrap[data-mode="grid"]{height:650px}.controls{gap:3px 15px}.unit{width:100%;min-height:30px;display:flex;align-items:center}.map-link{margin-left:auto;gap:10px}.mode button{padding:8px 8px}.static-label{font-size:11px}.controls>.static-label{max-width:110px}}
</style>
