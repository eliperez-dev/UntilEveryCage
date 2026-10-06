<script lang="ts">
  import { tick } from 'svelte';
  let { value, label, showValue = false, buttonLabel = 'Copy' }: { value: string; label: string; showValue?: boolean; buttonLabel?: string } = $props();
  let feedback = $state('');
  let fallback = $state(false);
  let input = $state<HTMLInputElement>();
  $effect(() => { void value; feedback = ''; fallback = false; });
  async function copy() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error();
      await navigator.clipboard.writeText(value); feedback = `${label} copied.`;
    } catch {
      fallback = true; await tick(); input?.focus(); input?.select(); feedback = `Select and copy the ${label.toLowerCase()} below.`;
    }
  }
</script>
<div class="copy-value">
  {#if showValue || fallback}<label>{label}<input bind:this={input} readonly {value} autocomplete="off" onfocus={event => event.currentTarget.select()} /></label>{/if}
  <button type="button" onclick={copy} disabled={!value} aria-label={`Copy ${label.toLowerCase()}`}>{buttonLabel}</button>
  <span role="status" aria-live="polite">{feedback}</span>
</div>
<style>
  .copy-value{min-width:0;display:flex;flex-wrap:wrap;align-items:end;gap:.4rem .6rem}label{display:grid;gap:.35rem;flex:1 1 14rem;min-width:0;color:#eee9df;font:.9rem/1.5 system-ui,sans-serif}input{box-sizing:border-box;width:100%;min-height:2.5rem;padding:.45rem .6rem;border:1px solid #59615c;border-radius:2px;background:#202523;color:#f4f1e9;font:.83rem ui-monospace,monospace}button{min-height:2.5rem;padding:.45rem .7rem;border:1px solid #657466;background:#252f28;color:#f4f1e9;cursor:pointer;font:.85rem system-ui,sans-serif}span{flex-basis:100%;color:#c6d0c5;font:.8rem/1.4 system-ui,sans-serif}span:empty{display:none}button:focus-visible,input:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}
</style>
