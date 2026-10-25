<script lang="ts">
  import ApplicationVersion from './ApplicationVersion.svelte';
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  const dataHref = $derived(`#/database/downloads${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`);
</script>

<footer class="project-footer" aria-label="Project information">
  <p>An independent, open-source, ad-free project.</p>
  <p class="links"><a href="mailto:untileverycageproject@protonmail.com">Contact</a> · <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">GitHub</a> · <a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noreferrer">Discord</a> · <a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">Support the project</a> · <a href="https://linktr.ee/veganresource" target="_blank" rel="noreferrer">Vegan resources</a></p>
  <p class="credits">Code is available under <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank" rel="noreferrer">AGPLv3 or later</a>. The project data compilation is CC BY-NC-SA where applicable; source data may have additional terms. Counter Adapted from <a href="https://www.adaptt.org/" target="_blank" rel="noreferrer">ADAPTT</a>. Original website inspired by <a href="https://finalnail.com/" target="_blank" rel="noreferrer">Final Nail</a>. <a href={dataHref}>Data reuse terms</a>.</p>
  <div class="application-version-slot"><ApplicationVersion /></div>
</footer>

<style>
  .project-footer{width:min(100% - 3rem,72rem);margin:0 auto;padding:1rem 0 1.25rem;border-top:1px solid #3d4740;color:#b8c4b7;font:.85rem/1.5 system-ui,sans-serif}
  p{margin:0}p+p{margin-top:.45rem}.credits{font-size:.82rem}.application-version-slot{min-height:0}
  a{color:#dce8d9;text-underline-offset:.2em}a:hover{color:#f1efe8}
  a:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}
  @media(max-width:40rem){.project-footer{width:calc(100% - 2rem)}}
</style>
