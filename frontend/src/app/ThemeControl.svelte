<script lang="ts">
  import { onMount } from 'svelte';
  import { getTheme, setTheme, subscribeTheme, type Theme } from '../features/theme/theme';
  import { language, tr } from './language';

  let theme = $state<Theme>('dark');
  const nextTheme = $derived(theme === 'dark' ? 'light' : 'dark');
  onMount(() => {
    theme = getTheme();
    return subscribeTheme(value => theme = value);
  });
</script>

<button class="theme-toggle" type="button" aria-label={tr(theme === 'light' ? 'Light theme' : 'Dark theme', $language)} aria-pressed={theme === 'light'} title={tr(theme === 'light' ? 'Light theme' : 'Dark theme', $language)} onclick={() => setTheme(nextTheme)}>
  <svg viewBox="0 0 24 24" aria-hidden="true" data-current-theme={theme}>
    {#if theme === 'dark'}
      <path d="M20.2 15.1A8.2 8.2 0 0 1 8.9 3.8a8.3 8.3 0 1 0 11.3 11.3Z" />
    {:else}
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" />
    {/if}
  </svg>
</button>

<style>
  .theme-toggle { display:grid; place-items:center; flex:none; width:2.1rem; height:2.1rem; min-height:2.1rem; aspect-ratio:1; padding:0; border:1px solid #536158; background:#1a201c; color:#f1efe8; cursor:pointer; }
  .theme-toggle svg { width:1rem; height:1rem; fill:none; stroke:currentColor; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round; }
</style>
