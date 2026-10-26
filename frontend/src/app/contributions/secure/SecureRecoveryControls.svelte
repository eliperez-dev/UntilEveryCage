<script lang="ts">
  import { language, tr } from '../../language';
  import { requestRecoveryDownload } from './secureUi';
  let { encryptedExport, recoverySecret, caseId, reviewer = false }: { encryptedExport: string; recoverySecret: string; caseId?: string; reviewer?: boolean } = $props();
  let keyVisible = $state(false), downloadState = $state<'idle' | 'requested' | 'failed'>('idle'), copyState = $state<'idle' | 'copied' | 'failed'>('idle');
  function download() {
    try { requestRecoveryDownload(encryptedExport, caseId); downloadState = 'requested'; }
    catch { downloadState = 'failed'; }
  }
  async function copy() {
    try { if (!navigator.clipboard?.writeText) throw new Error(); await navigator.clipboard.writeText(recoverySecret); copyState = 'copied'; }
    catch { copyState = 'failed'; }
  }
</script>
<section class="recovery-controls" aria-label={tr('Recovery access', $language)}>
  <h3>{tr(reviewer ? 'Keep your reviewer key' : 'Keep your recovery access', $language)}</h3>
  <p>{tr(reviewer ? 'Keep the file and recovery key to unlock review on another device.' : 'Keep the file and recovery key to reopen this inbox on another device.', $language)}</p>
  <button type="button" onclick={download}>{tr(reviewer ? 'Download encrypted reviewer key' : 'Download recovery file', $language)}</button>
  {#if downloadState === 'requested'}<p class="feedback" role="status">{tr('Download requested. Check your downloads.', $language)}</p>{:else if downloadState === 'failed'}<p class="feedback" role="alert">{tr('The download could not be started. Try again.', $language)}</p>{/if}
  <label>{tr('Recovery key', $language)}<input type={keyVisible ? 'text' : 'password'} value={recoverySecret} readonly autocomplete="off" spellcheck="false" /></label>
  <div class="key-actions"><button type="button" aria-pressed={keyVisible} onclick={() => keyVisible = !keyVisible}>{tr(keyVisible ? 'Hide key' : 'Show key', $language)}</button><button type="button" onclick={copy}>{tr(copyState === 'copied' ? 'Copied' : 'Copy recovery key', $language)}</button></div>
  {#if copyState === 'failed'}<p class="feedback" role="alert">{tr('The key could not be copied. Select it and copy it manually.', $language)}</p>{/if}
</section>
<style>
  .recovery-controls{display:grid;gap:.75rem;margin-top:1.5rem;padding-top:1.2rem;border-top:1px solid var(--line);color:var(--ink);font:.85rem/1.5 system-ui,sans-serif;min-width:0}h3{font-size:.9rem;font-weight:500;margin:0}p{font-size:.8rem;color:var(--ink-muted);margin:0}button{justify-self:start;min-height:2.75rem;padding:.55rem .8rem;border:1px solid var(--line-strong);background:transparent;color:var(--ink);font:inherit;cursor:pointer}button:hover{background:var(--panel-hover)}label{display:grid;gap:.4rem;font-size:.8rem}input{width:100%;min-width:0;min-height:2.75rem;padding:.6rem .75rem;border:1px solid var(--line-strong);border-radius:0;background:var(--panel);color:var(--ink);font:400 .85rem/1.5 ui-monospace,monospace}.key-actions{display:flex;align-items:center;gap:.65rem;flex-wrap:wrap}.feedback{color:var(--ink)}:is(input,button):focus-visible{outline:3px solid var(--focus);outline-offset:3px}@media(max-width:38rem){input{font-size:1rem}}
</style>
