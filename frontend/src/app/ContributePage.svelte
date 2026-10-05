<script lang="ts">
  let { enabled, targetRecordId = '', returnMapHref = '#/map' }: { enabled: boolean; targetRecordId?: string; returnMapHref?: string } = $props();
  const route = (path: string) => {
    if (path === 'contribution-status') return `#/contribution-status${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`;
    if (path === 'community') return `#/community${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`;
    if (path === 'bug') return `#/contribute/bug${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`;
    const params = new URLSearchParams();
    if (targetRecordId) params.set('target', targetRecordId);
    if (returnMapHref !== '#/map') params.set('map', returnMapHref);
    return `#/contribute/${path}${params.size ? `?${params}` : ''}`;
  };
</script>

<svelte:head><title>Contribute · Until Every Cage</title><meta name="description" content="Share a source, correction, or other useful contribution to Until Every Cage." /></svelte:head>

<section class="editorial-page contribute-page" aria-label="Contribute">
  <header class="intro"><h1>Contribute</h1><p class="lede">Help improve the map. Add a facility, share evidence, or tell us what needs fixing.</p><p class="privacy-note">We review submissions before anything is published.</p></header>
  <section class="contribution-tools" aria-labelledby="tools-heading"><div class="section-heading"><h2 id="tools-heading">Share information</h2></div>
    <div class="tool-list">
      <a href={route('facility')}><span><strong>Add a facility</strong><small>Share a facility name and any public source you have.</small></span><span class="arrow" aria-hidden="true">→</span></a>
      <a href={route('evidence')}><span><strong>Add evidence</strong><small>Share a link or describe evidence related to a record.</small></span><span class="arrow" aria-hidden="true">→</span></a>
      <a href={route('correction')}><span><strong>Suggest a correction</strong><small>Tell us what seems wrong or incomplete.</small></span><span class="arrow" aria-hidden="true">→</span></a>
      <a href={route('duplicate')}><span><strong>Report a possible duplicate</strong><small>Point to two records that may describe the same entry.</small></span><span class="arrow" aria-hidden="true">→</span></a>
      <a href={route('privacy-removal')}><span><strong>Request a privacy review</strong><small>Flag a location or detail that may expose a person.</small></span><span class="arrow" aria-hidden="true">→</span></a>
      <a href={route('contribution-status')}><span><strong>Check a receipt</strong><small>Look up status using the receipt shown after submission.</small></span><span class="arrow" aria-hidden="true">→</span></a>
      <a href={route('community')}><span><strong>Browse community submissions</strong><small>Open the separate view of claims that passed privacy screening.</small></span><span class="arrow" aria-hidden="true">→</span></a>
      <a href={route('bug')}><span><strong>Report a bug</strong><small>Describe a problem and prepare an email draft or public issue.</small></span><span class="arrow" aria-hidden="true">→</span></a>
    </div>
    {#if !enabled}<p class="availability" role="status">Contribution forms are not available in this build. You can still contact the project or explore the source code.</p>{/if}
  </section>
  <section class="ways-to-help" aria-labelledby="support-heading"><div><h2 id="support-heading">Support the project</h2><p>Help with the project, share a resource, or support the work of maintaining this public research tool.</p></div>
    <ul class="support-links">
      <li><a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">Explore the project on GitHub <span aria-hidden="true">↗</span></a></li>
      <li><a href="https://discord.gg/wbdTHzAZ4b" target="_blank" rel="noreferrer">Join the project Discord <span aria-hidden="true">↗</span></a></li>
      <li><a href="https://ko-fi.com/untileverycageisempty" target="_blank" rel="noreferrer">Support the project on Ko-fi <span aria-hidden="true">↗</span></a></li>
      <li><a href="https://linktr.ee/veganresource" target="_blank" rel="noreferrer">Explore vegan resources <span aria-hidden="true">↗</span></a></li>
      <li><a href="mailto:untileverycageproject@protonmail.com">Email the project <span aria-hidden="true">↗</span></a></li>
      <li><a href="https://github.com/eliperez-dev/UntilEveryCage/issues/new" target="_blank" rel="noreferrer">Report a public issue <span aria-hidden="true">↗</span></a></li>
    </ul>
  </section>
</section>

<style>
  .editorial-page{width:min(100% - 3rem,72rem);margin:auto;padding:clamp(2.4rem,6vw,5rem) 0 6rem;color:#f1efe8;font:1rem/1.6 ui-sans-serif,system-ui,sans-serif}.intro{max-width:49rem;padding-bottom:3rem;border-bottom:1px solid #485149}.editorial-page h1{margin:.4rem 0 1rem;font:400 clamp(2.8rem,7vw,5rem)/1.04 Georgia,serif;letter-spacing:-.04em}.editorial-page h2{margin:0;font:400 clamp(1.7rem,3.5vw,2.5rem)/1.15 Georgia,serif}.lede{max-width:43rem;margin:0;color:#d3dbd1;font-size:clamp(1.04rem,1.5vw,1.2rem)}.privacy-note{margin:1.2rem 0 0;padding-left:.8rem;border-left:2px solid #9a7556;color:#c6c7be;font-size:.88rem}.contribution-tools{display:grid;grid-template-columns:minmax(13rem,.85fr) minmax(0,2fr);gap:2.2rem;padding:2.5rem 0;border-bottom:1px solid #485149}.section-heading h2{max-width:15rem}.tool-list{border-top:1px solid #485149}.tool-list a{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:.75rem;padding:1rem .2rem;border-bottom:1px solid #3b443e;color:#f1efe8;text-decoration:none}.tool-list a:hover{background:#202622}.tool-list strong,.tool-list small{display:block}.tool-list strong{font-weight:650}.tool-list small{margin-top:.18rem;color:#bfc6bc;font-size:.8rem}.arrow{color:#d4bc93}.availability{grid-column:2;color:#e3c9a6;font-size:.86rem}.ways-to-help{display:grid;grid-template-columns:minmax(13rem,.85fr) minmax(0,2fr);gap:2.2rem;padding:2.5rem 0}.ways-to-help p{max-width:26rem;color:#bec8bf;font-size:.88rem}.support-links{margin:0;padding:0;list-style:none;border-top:1px solid #485149}.support-links li{border-bottom:1px solid #3b443e}.support-links a{display:flex;justify-content:space-between;gap:1rem;padding:.8rem .2rem;color:#dce8d9;text-underline-offset:.25em}.support-links a:hover{color:#fff}.editorial-page a:focus-visible{outline:2px solid #f1efe8;outline-offset:3px}@media(max-width:48rem){.editorial-page{width:min(100% - 2rem,72rem)}.contribution-tools,.ways-to-help{grid-template-columns:1fr;gap:1.2rem}.section-heading h2{max-width:none}.availability{grid-column:1}.tool-list a{grid-template-columns:minmax(0,1fr) auto}}
</style>
