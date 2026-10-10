<script lang="ts">
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  const dataHref = $derived(`#/database/downloads${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`);
</script>

<footer class="project-footer" aria-label="Project information">
  <p>An independent, open-source project. <a href="mailto:untileverycageproject@protonmail.com">Get in touch</a> with feedback, or <a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">support its hosting and data work</a>.</p>
  <p class="credits">Code: <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank" rel="noreferrer">AGPLv3 or later</a> · Data: <a href={dataHref}>reuse terms</a>. Original website inspired by <a href="https://finalnail.com/" target="_blank" rel="noreferrer">Final Nail</a>.</p>
</footer>

<style>
  .project-footer{width:min(100% - 3rem,46rem);margin:0 auto;padding:1rem 0 1.25rem;border-top:1px solid #3d4740;color:#b8c4b7;font:.85rem/1.5 system-ui,sans-serif}
  p{margin:0}p+p{margin-top:.45rem}.credits{font-size:.82rem}
  a{color:#dce8d9;text-underline-offset:.2em}a:hover{color:#f1efe8}
  a:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}
  @media(max-width:40rem){.project-footer{width:calc(100% - 2rem)}}
</style>
