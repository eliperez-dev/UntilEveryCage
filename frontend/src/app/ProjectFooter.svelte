<script lang="ts">
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  const href = (path: string) => `#/${path}${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`;
</script>

<footer class="project-footer" aria-label="Project information">
  <p class="identity">An independent, open-source project.</p>
  <nav aria-label="Project links">
    <a href="mailto:untileverycageproject@protonmail.com">Contact</a>
    <a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">Support on Ko-fi</a>
    <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">GitHub</a>
    <a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noreferrer">Discord</a>
    <a href="https://linktr.ee/veganresource" target="_blank" rel="noreferrer">Resources</a>
  </nav>
  <nav aria-label="Help and feedback">
    <a href={href('about/help')}>Help</a>
    <a href={href('contribute/bug')}>Report a bug</a>
    <a href={href('contribute/privacy-removal')}>Privacy or removal</a>
    <a href={href('about/sources')}>Sources & methodology</a>
  </nav>
  <p class="licenses">Code: <a href="https://www.gnu.org/licenses/agpl-3.0.html" target="_blank" rel="noreferrer">AGPLv3 or later</a> · Data: <a href={href('database/downloads')}>reuse terms</a></p>
</footer>

<style>
  .project-footer{max-width:96rem;margin:0 auto;padding:1rem 1.5rem;border-top:1px solid #3d4740;color:#b8c4b7;font:.85rem/1.5 system-ui,sans-serif}
  p{margin:0}.identity{margin-bottom:.35rem}.licenses{margin-top:.45rem;font-size:.82rem}
  nav{display:flex;flex-wrap:wrap;column-gap:1.25rem;row-gap:.1rem}
  nav a{display:inline-flex;align-items:center;min-height:2rem}
  a{color:#dce8d9;text-underline-offset:.2em}a:hover{color:#f1efe8}
  a:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}
  @media(any-pointer:coarse){nav a{min-height:2.75rem}}
  @media(max-width:40rem){.project-footer{padding:1rem}}
</style>
