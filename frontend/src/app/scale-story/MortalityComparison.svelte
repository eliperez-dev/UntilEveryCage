<script lang="ts">
  import { onMount } from 'svelte';
  import { language } from '../language';
  import { storyMessages } from './messages';
  import { ActiveStoryClock, CHICKEN_LINE_RATE, lineParticles } from './engine';
  let { mapHref }: { mapHref: string } = $props();
  const text = $derived(storyMessages($language));
  let paused = $state(false), reduced = $state(true), canvas: HTMLCanvasElement;
  let syncRuntime: (() => void) | null = null;
  function togglePause() { paused = !paused; syncRuntime?.(); }
  onMount(() => {
    const ctx = canvas.getContext('2d'); if (!ctx) return;
    const clock = new ActiveStoryClock(), preference = matchMedia('(prefers-reduced-motion: reduce)');
    let width = 1, height = 1, visible = false, frame = 0, disposed = false, lastDiagnostic = 0;
    function human(x: number, y: number, dead: boolean) {
      ctx!.strokeStyle = dead ? '#919392' : '#f2f0e8'; ctx!.fillStyle = ctx!.strokeStyle; ctx!.lineWidth = 1.6;
      ctx!.beginPath(); ctx!.arc(x, y - 7, 3.3, 0, Math.PI * 2); ctx!.fill();
      ctx!.beginPath(); ctx!.moveTo(x, y - 2); ctx!.lineTo(x, y + 9); ctx!.moveTo(x - 5, y + 2); ctx!.lineTo(x + 5, y + 2);
      ctx!.moveTo(x - 4, y + 17); ctx!.lineTo(x, y + 9); ctx!.lineTo(x + 4, y + 17); ctx!.stroke();
    }
    function chicken(x: number, y: number, dead: boolean) {
      ctx!.strokeStyle = dead ? '#d74749' : '#f2f0e8'; ctx!.fillStyle = ctx!.strokeStyle; ctx!.lineWidth = 1.3;
      ctx!.beginPath(); ctx!.ellipse(x - 1, y + 2, 7, 5, 0, 0, Math.PI * 2); ctx!.fill();
      ctx!.beginPath(); ctx!.arc(x + 6, y - 5, 3.4, 0, Math.PI * 2); ctx!.fill();
      ctx!.beginPath(); ctx!.moveTo(x + 9, y - 6); ctx!.lineTo(x + 13, y - 3); ctx!.lineTo(x + 9, y - 2); ctx!.closePath(); ctx!.fill();
      ctx!.beginPath(); ctx!.moveTo(x + 3, y - 8); ctx!.lineTo(x + 4, y - 12); ctx!.lineTo(x + 6, y - 10); ctx!.lineTo(x + 8, y - 12); ctx!.lineTo(x + 9, y - 7); ctx!.fill();
      ctx!.beginPath(); ctx!.moveTo(x - 7, y + 1); ctx!.lineTo(x - 12, y - 5); ctx!.lineTo(x - 8, y + 4);
      ctx!.moveTo(x - 3, y + 6); ctx!.lineTo(x - 3, y + 12); ctx!.lineTo(x + 1, y + 12);
      ctx!.moveTo(x + 2, y + 6); ctx!.lineTo(x + 2, y + 11); ctx!.lineTo(x + 6, y + 11); ctx!.stroke();
    }
    function render() {
      if (disposed) return;
      ctx!.clearRect(0, 0, width, height);
      const gap = width < 500 ? 22 : 60, lane = (width - gap) / 2, seconds = reduced ? 1.68 : clock.elapsed;
      ctx!.lineWidth = 1; ctx!.strokeStyle = '#919392'; ctx!.beginPath(); ctx!.moveTo(0, height * .48); ctx!.lineTo(lane, height * .48); ctx!.stroke();
      ctx!.strokeStyle = '#d74749'; ctx!.beginPath(); ctx!.moveTo(lane + gap, height * .48); ctx!.lineTo(width, height * .48); ctx!.stroke();
      lineParticles(seconds, 2, lane, height, (_id, x, y, dead) => human(x, y, dead));
      lineParticles(seconds, CHICKEN_LINE_RATE, lane, height, (_id, x, y, dead) => chicken(x + lane + gap, y, dead));
    }
    function resize() {
      const rect = canvas.getBoundingClientRect(), ratio = Math.min(2, devicePixelRatio || 1);
      width = Math.max(1, rect.width); height = Math.max(1, rect.height); canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      ctx!.setTransform(ratio, 0, 0, ratio, 0, 0); render();
    }
    const shouldRun = () => !disposed && visible && !paused && !reduced && !document.hidden;
    function publish() { canvas.dataset.emitted = String(clock.emitted(CHICKEN_LINE_RATE)); canvas.dataset.humanEmitted = String(clock.emitted(2)); }
    function tick(now: number) { frame = 0; if (!shouldRun()) return; clock.advance(now); render(); if (now - lastDiagnostic > 250) { publish(); lastDiagnostic = now; } if (shouldRun()) frame = requestAnimationFrame(tick); }
    function sync() { clock.setRunning(shouldRun(), performance.now()); publish(); canvas.dataset.state = reduced ? 'static' : paused ? 'paused' : shouldRun() ? 'running' : 'offscreen'; if (shouldRun()) { if (!frame) frame = requestAnimationFrame(tick); } else { cancelAnimationFrame(frame); frame = 0; } }
    function preferenceChanged() { reduced = preference.matches; sync(); render(); }
    const observer = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? false; sync(); });
    const resizeObserver = new ResizeObserver(resize); observer.observe(canvas); resizeObserver.observe(canvas);
    preference.addEventListener('change', preferenceChanged); document.addEventListener('visibilitychange', sync); syncRuntime = sync; preferenceChanged(); resize();
    return () => { disposed = true; syncRuntime = null; cancelAnimationFrame(frame); observer.disconnect(); resizeObserver.disconnect(); preference.removeEventListener('change', preferenceChanged); document.removeEventListener('visibilitychange', sync); clock.setRunning(false, performance.now()); canvas.width = 1; canvas.height = 1; };
  });
</script>

<div class="mortality-comparison">
  <div class="lane-headings"><div><strong>{text.humans}</strong><span>2 / s</span></div><div><strong>{text.chickens}</strong><span>≈ {CHICKEN_LINE_RATE.toLocaleString($language, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} / s</span></div></div>
  <div class="line-labels" aria-hidden="true"><span>{text.allCauseDeaths}</span><span>{text.slaughtered}</span></div>
  <div class="line-field" role="img" aria-label={text.lineCanvas}><canvas bind:this={canvas} aria-hidden="true"></canvas></div>
  <div class="lane-captions"><p>{text.humanDate}</p><p>{text.chickenRate}<br /><small>{text.chickenDate}</small></p></div>
  <div class="controls">{#if reduced}<span>{text.staticView}</span>{:else}<button type="button" class="pause" aria-pressed={paused} onclick={togglePause}>{paused ? text.resume : text.pause}</button>{/if}<a class="map-link" href={mapHref}>{text.openMap}<span aria-hidden="true">↗</span></a></div>
</div>

<style>
  .mortality-comparison{--line-label-red:#e87c7d}
  :global(:root[data-theme="light"]) .mortality-comparison{--line-label-red:#a92a30}
  .mortality-comparison{margin-top:33px}.lane-headings{display:grid;grid-template-columns:1fr 1fr;gap:60px}.lane-headings>div{display:flex;justify-content:space-between;gap:14px;align-items:baseline;border-top:1px solid var(--story-line);padding-top:20px}.lane-headings strong{font-size:14px;font-weight:500}.lane-headings span{font:30px/1.1 Georgia,serif;letter-spacing:-.03em}.line-field{height:380px;margin-top:12px;background:#141414}canvas{display:block;width:100%;height:100%}.line-labels{display:grid;grid-template-columns:1fr 1fr;gap:60px;font-size:12px;margin-top:14px}.line-labels>span{color:var(--story-muted)}.line-labels>span+span{color:var(--line-label-red)}.lane-captions{display:grid;grid-template-columns:1fr 1fr;gap:60px;margin-top:14px;font-size:12px;line-height:1.7;color:var(--story-muted)}p{margin:0}.lane-captions small{font-size:12px}.controls{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:22px;border-bottom:1px solid var(--story-line);padding:10px 0;font-size:12px}.controls>span{margin-right:auto;color:var(--story-muted)}button,a{font:inherit;color:inherit;min-height:44px}button{padding:8px;border:0;background:none;cursor:pointer;min-width:62px}.map-link{display:flex;align-items:center;gap:22px;text-decoration:none;border-bottom:1px solid var(--story-muted)}button:focus-visible,a:focus-visible{outline:2px solid #d74749;outline-offset:4px}
  @media(max-width:700px){.lane-headings,.lane-captions,.line-labels{gap:22px}.lane-headings>div{display:block}.lane-headings span{display:block;margin-top:12px;font-size:29px}.line-field{height:350px}.lane-captions{font-size:12px;line-height:1.6}.controls{gap:18px}}
</style>
