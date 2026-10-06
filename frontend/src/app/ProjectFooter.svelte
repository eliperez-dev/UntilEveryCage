<script lang="ts">
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  const href = (path: string) => `#/${path}${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`;
</script>
<footer class="project-footer" aria-label="Project information">
  <nav aria-label="Project links"><a href="mailto:untileverycageproject@protonmail.com">Email</a><a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">Ko-fi</a><a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">GitHub</a><a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noreferrer">Discord</a><a href="https://linktr.ee/veganresource" target="_blank" rel="noreferrer">Resources</a></nav>
  <p>Code: AGPLv3 or later · Data: <a href={href('database/downloads')}>reuse terms</a></p>
</footer>
<style>
  .project-footer{max-width:96rem;margin:0 auto;padding:1rem 1.5rem;border-top:1px solid #3d4740;color:#b8c4b7;font:.82rem/1.5 system-ui,sans-serif}nav{display:flex;flex-wrap:wrap;gap:.45rem 1.2rem}p{margin:.6rem 0 0}a{color:#dce8d9;text-underline-offset:.2em}a:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:40rem){.project-footer{padding:1rem}}
</style>
