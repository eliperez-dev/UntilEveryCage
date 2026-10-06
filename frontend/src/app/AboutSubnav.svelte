<script lang="ts">
  let { current, returnMapHref = '#/map' }: { current: 'overview' | 'manifesto' | 'sources'; returnMapHref?: string } = $props();
  const href = (path: string) => `${path}${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`;
</script>

<nav class="about-subnav" aria-label="About">
  <a href={href('#/about')} aria-current={current === 'overview' ? 'page' : undefined}>Overview</a>
  <a href={href('#/about/manifesto')} aria-current={current === 'manifesto' ? 'page' : undefined}>Manifesto</a>
  <a href={href('#/about/sources')} aria-current={current === 'sources' ? 'page' : undefined}>Sources & methodology</a>
</nav>

<style>
  .about-subnav{display:flex;flex-wrap:wrap;gap:.55rem 1.4rem;padding:0 0 1.1rem;border-bottom:1px solid #4a554b;font: .82rem ui-sans-serif,system-ui,sans-serif}.about-subnav a{color:#cbd6cb;text-underline-offset:.25em}.about-subnav a[aria-current]{color:#f1efe8;font-weight:650}.about-subnav a:focus-visible{outline:2px solid #f1efe8;outline-offset:3px}
</style>
