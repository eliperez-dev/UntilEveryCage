<script lang="ts">
  import { onMount } from 'svelte';
  import { getTheme, setTheme, subscribeTheme, type Theme } from '../features/theme/theme';
  import { language, tr } from './language';

  let theme = $state<Theme>('dark');
  onMount(() => {
    theme = getTheme();
    return subscribeTheme(value => theme = value);
  });
</script>

<label class="theme-field">{tr('Theme', $language)}
  <select aria-label={tr('Theme', $language)} value={theme} onchange={(event) => setTheme(event.currentTarget.value === 'light' ? 'light' : 'dark')}>
    <option value="dark">{tr('Dark theme', $language)}</option>
    <option value="light">{tr('Light theme', $language)}</option>
  </select>
</label>

<style>
  .theme-field { display: grid; gap: .35rem; font-size: .8125rem; }
  select { width: 100%; min-height: 44px; padding: .45rem .6rem; background: var(--ui-raised); color: var(--ui-ink); border: 1px solid var(--ui-line); font: inherit; }
</style>
