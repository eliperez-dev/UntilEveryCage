<script lang="ts">
  import { onMount } from 'svelte';
  import { getTheme, setTheme, subscribeTheme, type Theme } from '../features/theme/theme';

  let { label = 'Appearance', lightLabel = 'Light', darkLabel = 'Dark' }: { label?: string; lightLabel?: string; darkLabel?: string } = $props();
  let theme = $state<Theme>('dark');
  onMount(() => {
    theme = getTheme();
    return subscribeTheme(value => theme = value);
  });
</script>

<section class="theme-control" aria-label={label}>
  <p class="theme-control-label">{label}</p>
  <div class="theme-control-options" role="group" aria-label="Color theme">
    <button type="button" aria-pressed={theme === 'light'} onclick={() => setTheme('light')}>{lightLabel}</button>
    <button type="button" aria-pressed={theme === 'dark'} onclick={() => setTheme('dark')}>{darkLabel}</button>
  </div>
</section>
