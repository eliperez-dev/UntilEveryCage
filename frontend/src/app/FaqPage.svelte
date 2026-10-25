<script lang="ts">
  import { language, tr } from './language';
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
  <h1 id="faq-title">{tr('Frequently asked questions', $language)}</h1>
  <section id="technology" aria-labelledby="technology-title">
    <span id="records" aria-hidden="true"></span>
    <h2 id="technology-title">{tr('How the data reaches the map', $language)}</h2>
    <p>{tr('Government datasets are collected, cleaned and standardized, with links back to their sources. Address lookups add coordinates, and matching connects related records. Dated releases supply the map, search and downloads through a Rust API.', $language)}</p>
  </section>
  <section id="contributions" aria-labelledby="contributions-title">
    <h2 id="contributions-title">{tr('Contributions', $language)}</h2>
    <p>{tr('You can suggest a facility, add evidence, suggest a correction, report a possible duplicate, or request a privacy review. Submissions are reviewed separately from the project dataset and do not automatically change a release.', $language)}</p>
    <p>{tr('After submitting, keep the private tracking link shown with your receipt to check its status.', $language)}</p>
    <p><a href={route('contribute')}>{tr('Contribute to the project', $language)}</a></p>
  </section>
  <section id="help" aria-labelledby="help-title">
    <h2 id="help-title">{tr('Help, support, and contact', $language)}</h2>
    <p>{tr('For a website problem,', $language)} <a href={route('contribute/bug')}>{tr('report a bug', $language)}</a> {tr('or', $language)} <a href="mailto:untileverycageproject@protonmail.com">{tr('contact the project', $language)}</a>.</p>
    <p>{tr('Code contributions and issues are on', $language)} <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">GitHub</a>. {tr('You can also join', $language)} <a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noreferrer">{tr('project Discord', $language)}</a> {tr('or', $language)} <a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">{tr('support the project', $language)}</a>.</p>
  </section>
</article>
<style>
  .faq-page{width:min(100% - 3rem,48rem);margin:auto;padding:1.5rem 0 2.5rem;color:var(--ink);font:.9rem/1.55 system-ui,sans-serif}section{scroll-margin-top:1rem;margin:0 0 1.6rem}h1{margin:0 0 1.2rem;font:500 2rem/1.2 Georgia,serif;letter-spacing:-.02em}h2{margin:0 0 .55rem;font:600 1.12rem/1.35 system-ui,sans-serif}p{margin:0 0 .7rem;color:var(--ink-muted)}a{color:var(--link);text-underline-offset:.2em;overflow-wrap:anywhere}@media(max-width:40rem){.faq-page{width:calc(100% - 2rem);padding-top:1.2rem}h1{font-size:1.7rem}}
</style>
