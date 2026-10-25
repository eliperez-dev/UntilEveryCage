<script lang="ts">
  import { language, tr } from './language';
  import ApplicationVersion from './ApplicationVersion.svelte';
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  const dataHref = $derived(`#/database/downloads${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`);
</script>

<footer class="project-footer" aria-label={tr('Project information', $language)}>
  <p>{tr('An independent, open-source, ad-free project.', $language)}</p>
  <p class="links"><a href="mailto:untileverycageproject@protonmail.com">{tr('Contact', $language)}</a> · <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">GitHub</a> · <a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noreferrer">Discord</a> · <a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">{tr('Support the project', $language)}</a> · <a href="https://linktr.ee/veganresource" target="_blank" rel="noreferrer">{tr('Vegan resources', $language)}</a></p>
  <p class="credits">{tr('Code is available under', $language)} <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank" rel="noreferrer">AGPLv3 {tr('or later', $language)}</a>. {tr('The project data compilation is CC BY-NC-SA where applicable; source data may have additional terms.', $language)} {tr('Counter Adapted from', $language)} <a href="https://www.adaptt.org/" target="_blank" rel="noreferrer">ADAPTT</a>. {tr('Original website inspired by', $language)} <a href="https://finalnail.com/" target="_blank" rel="noreferrer">Final Nail</a>. <a href={dataHref}>{tr('Data reuse terms', $language)}</a>.</p>
  <div class="application-version-slot"><ApplicationVersion /></div>
</footer>

<style>
  .project-footer{width:min(100% - 3rem,72rem);margin:0 auto;padding:1rem 0 1.25rem;border-top:1px solid #3d4740;color:#b8c4b7;font:.85rem/1.5 system-ui,sans-serif}
  p{margin:0}p+p{margin-top:.45rem}.credits{font-size:.82rem}.application-version-slot{min-height:0}
  a{color:#dce8d9;text-underline-offset:.2em}a:hover{color:#f1efe8}
  a:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}
  @media(max-width:40rem){.project-footer{width:calc(100% - 2rem)}}
</style>
