<script lang="ts">
  let { section, returnMapHref = '#/map' }: { section?: 'technology' | 'records' | 'contributions' | 'help' | undefined; returnMapHref?: string } = $props();
  const context = $derived(returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : '');
  const route = (path: string) => `#/${path}${context ? `${path.includes('?') ? '&' : '?'}map=${encodeURIComponent(returnMapHref)}` : ''}`;
  $effect(() => {
    const id = section;
    if (id) requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }));
  });
</script>
<svelte:head><title>FAQ · Until Every Cage</title><meta name="description" content="How the data reaches the map, contributions, and help for Until Every Cage." /></svelte:head>
<article class="faq-page" aria-labelledby="faq-title">
  <h1 id="faq-title">Frequently asked questions</h1>
  <section id="technology" aria-labelledby="technology-title">
    <span id="records" aria-hidden="true"></span>
    <h2 id="technology-title">How the data reaches the map</h2>
    <p>Government datasets are collected, cleaned and standardized, with links back to their sources. Address lookups add coordinates, and matching connects related records. Dated releases supply the map, search and downloads through a Rust API.</p>
  </section>
  <section id="contributions" aria-labelledby="contributions-title">
    <h2 id="contributions-title">Contributions</h2>
    <p>You can suggest a facility, add evidence, suggest a correction, report a possible duplicate, or request a privacy review. Submissions are reviewed separately from the project dataset and do not automatically change a release.</p>
    <p>After submitting, keep the private tracking link shown with your receipt to check its status.</p>
    <p><a href={route('contribute')}>Contribute to the project</a></p>
  </section>
  <section id="help" aria-labelledby="help-title">
    <h2 id="help-title">Help, support, and contact</h2>
    <p>For a website problem, <a href={route('contribute/bug')}>report a bug</a> or <a href="mailto:untileverycageproject@protonmail.com">contact the project</a>.</p>
    <p>Code contributions and issues are on <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">GitHub</a>. You can also join the <a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noreferrer">project Discord</a> or <a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">support the project</a>.</p>
  </section>
</article>
<style>
  .faq-page{width:min(100% - 3rem,48rem);margin:auto;padding:1.5rem 0 2.5rem;color:#f1efe8;font:.9rem/1.55 system-ui,sans-serif}section{scroll-margin-top:1rem;margin:0 0 1.6rem}h1{margin:0 0 1.2rem;font:500 2rem/1.2 Georgia,serif;letter-spacing:-.02em}h2{margin:0 0 .55rem;font:600 1.12rem/1.35 system-ui,sans-serif}p{margin:0 0 .7rem;color:#c6d0c5}a{color:#dce8d9;text-underline-offset:.2em;overflow-wrap:anywhere}@media(max-width:40rem){.faq-page{width:calc(100% - 2rem);padding-top:1.2rem}h1{font-size:1.7rem}}
</style>
