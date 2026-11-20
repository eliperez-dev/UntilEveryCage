<script lang="ts">
  import { onMount } from 'svelte';
  import { language } from '../language';
  import { storyMessages } from './messages';
  import { ActiveStoryClock, CHICKEN_LINE_RATE, lineParticles } from './engine';
  import StoryCounter from './StoryCounter.svelte';
  const text = $derived(storyMessages($language));
  let reduced = $state(true), canvas: HTMLCanvasElement;
  onMount(() => {
    let ctx: CanvasRenderingContext2D | null = null;
    const clock = new ActiveStoryClock(), preference = matchMedia('(prefers-reduced-motion: reduce)');
    let width = 1, height = 1, visible = false, frame = 0, disposed = false, lastDiagnostic = 0, resizePending = true, contextUnavailable = false;
    function dot(x: number, y: number, dead: boolean, outcome: string) {
      ctx!.fillStyle = dead ? outcome : '#f2f0e8';
      ctx!.beginPath(); ctx!.arc(x, y, 3, 0, Math.PI * 2); ctx!.fill();
    }
    function render() {
      if (disposed || !visible || document.hidden || !ctx) return;
      ctx!.clearRect(0, 0, width, height);
      const gap = width < 500 ? 22 : 60, lane = (width - gap) / 2, seconds = reduced ? 1.68 : clock.elapsed;
      ctx!.lineWidth = 1; ctx!.strokeStyle = '#919392'; ctx!.beginPath(); ctx!.moveTo(0, height * .48); ctx!.lineTo(lane, height * .48); ctx!.stroke();
      ctx!.strokeStyle = '#d74749'; ctx!.beginPath(); ctx!.moveTo(lane + gap, height * .48); ctx!.lineTo(width, height * .48); ctx!.stroke();
      lineParticles(seconds, 2, lane, height, (_id, x, y, dead) => dot(x, y, dead, '#919392'));
      lineParticles(seconds, CHICKEN_LINE_RATE, lane, height, (_id, x, y, dead) => dot(x + lane + gap, y, dead, '#d74749'));
    }
    function resize() {
      resizePending = true;
      if (disposed || !visible || document.hidden) return;
      ctx ??= canvas.getContext('2d');
      if (!ctx) { contextUnavailable = true; return; }
      const rect = canvas.getBoundingClientRect(), ratio = Math.min(2, devicePixelRatio || 1);
      width = Math.max(1, rect.width); height = Math.max(1, rect.height); canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      ctx!.setTransform(ratio, 0, 0, ratio, 0, 0); resizePending = false; render();
    }
    const shouldRun = () => !disposed && visible && !reduced && !document.hidden && !contextUnavailable;
    function publish() { canvas.dataset.emitted = String(clock.emitted(CHICKEN_LINE_RATE)); canvas.dataset.humanEmitted = String(clock.emitted(2)); canvas.dataset.initialized = String(ctx !== null); }
    function tick(now: number) { frame = 0; if (!shouldRun()) return; clock.advance(now); render(); if (now - lastDiagnostic > 250) { publish(); lastDiagnostic = now; } if (shouldRun()) frame = requestAnimationFrame(tick); }
    function sync() { clock.setRunning(shouldRun(), performance.now()); if (visible && !document.hidden) { if (resizePending || !ctx) resize(); else if (reduced) render(); } publish(); canvas.dataset.state = reduced ? 'static' : shouldRun() ? 'running' : 'offscreen'; if (shouldRun()) { if (!frame) frame = requestAnimationFrame(tick); } else { cancelAnimationFrame(frame); frame = 0; } }
    function preferenceChanged() { reduced = preference.matches; sync(); }
    const observer = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? false; sync(); });
    const resizeObserver = new ResizeObserver(resize); observer.observe(canvas); resizeObserver.observe(canvas);
    preference.addEventListener('change', preferenceChanged); document.addEventListener('visibilitychange', sync); preferenceChanged();
    return () => { disposed = true; cancelAnimationFrame(frame); observer.disconnect(); resizeObserver.disconnect(); preference.removeEventListener('change', preferenceChanged); document.removeEventListener('visibilitychange', sync); clock.setRunning(false, performance.now()); canvas.width = 1; canvas.height = 1; };
  });
</script>

<div class="mortality-comparison">
  <div class="lane-headings">
    <StoryCounter population="human" rate={2} label={text.humanSinceOpened} />
    <StoryCounter population="chicken" rate={CHICKEN_LINE_RATE} label={text.chickenSinceOpened} />
  </div>
  <div class="line-field" aria-hidden="true"><canvas bind:this={canvas}></canvas></div>
</div>

<style>
  .lane-headings { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 60px; }
  .line-field { height: 220px; margin-top: 8px; background: #141414; }
  canvas { display: block; width: 100%; height: 100%; }

  @media (max-width: 700px) {
    .lane-headings { gap: 22px; }
    .line-field { height: 200px; }
  }
</style>
