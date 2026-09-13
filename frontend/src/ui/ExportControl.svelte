<script lang="ts">
  export let enabled = false;
  export let busy = false;
  export let error = '';
  export let onExport: () => void;
</script>

<div class="export-control">
  <button disabled={!enabled || busy} onclick={onExport}>{busy ? 'Preparing CSV…' : 'Download eligible CSV'}</button>
  {#if !enabled}<p>CSV export is available only for an explicit official profile with a selected eligible release.</p>{/if}
  {#if error}<p class="export-error" role="alert">{error}</p>{/if}
</div>
