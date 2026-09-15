<script lang="ts">
  export let enabled = false;
  export let busy = false;
  export let error = '';
  export let profile = 'official';
  export let onExport: () => void;
</script>

<div class="export-control">
  <button disabled={!enabled || busy} onclick={onExport}>{busy ? 'Preparing CSV…' : `Download ${profile} CSV`}</button>
  {#if !enabled}<p>CSV export is available only when the selected V2 profile has an eligible promoted release.</p>{/if}
  {#if error}<p class="export-error" role="alert">{error}</p>{/if}
</div>
