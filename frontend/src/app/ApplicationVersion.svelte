<script lang="ts">
  import { onMount } from 'svelte';
  import { createApplicationVersionRepository } from '../api/ApplicationVersionRepository';

  let version = $state<string | null>(null);
  onMount(() => {
    let active = true;
    void createApplicationVersionRepository().current().then(result => { if (active) version = result?.version ?? null; });
    return () => { active = false; };
  });
</script>

{#if version}<span aria-label="Application version">v{version}</span>{/if}
