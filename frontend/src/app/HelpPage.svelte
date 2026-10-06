<script lang="ts">
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  const context = $derived(returnMapHref !== '#/map' ? `map=${encodeURIComponent(returnMapHref)}` : '');
  const route = (path: string, type?: string) => `#/${path}${context || type ? `?${[type ? `type=${type}` : '', context].filter(Boolean).join('&')}` : ''}`;
  const databaseHref = $derived(returnMapHref.includes('?') ? `#/database?${returnMapHref.split('?')[1]}` : '#/database');
  const video = `${import.meta.env.BASE_URL}tutorials/contribution-types.webm`;
</script>
<svelte:head><title>Help · Until Every Cage</title></svelte:head>
<section class="help-page" aria-labelledby="help-title">
  <h1 id="help-title">Help</h1>
  <section><h2>Explore</h2><ol><li>Open the <a href={returnMapHref}>Map</a> and search a place or facility. Use filters to narrow the results.</li><li>Choose a result to inspect its source, dates, location precision, and connections.</li><li>Use the <a href={databaseHref}>Database</a> to compare records and open their details.</li></ol></section>
  <section><h2>Contribute</h2><ol><li>Open <a href={route('contribute')}>Contribute</a> and choose a contribution type.</li><li>Facility adds a new tip. Evidence supports an existing record: paste its page link or ID, then add a source or describe what you found.</li><li>Send the form and save both receipt values. Use <a href={route('contribution-status')}>Check status</a> to follow the review.</li></ol>
    <figure><video controls muted preload="metadata" aria-label="How to choose a contribution type and open the evidence form" aria-describedby="tutorial-caption"><source src={video} type="video/webm" />Your browser cannot play this video. Follow the written steps above.</video><figcaption id="tutorial-caption">Silent demonstration: switch contribution types, then open Evidence. The steps above describe the same actions.</figcaption></figure>
  </section>
  <section><h2>Fix a problem</h2><p>Choose <a href={route('contribute','correction')}>Correction</a> for a record error, <a href={route('contribute','duplicate')}>Duplicate</a> for repeated records, or <a href={route('contribute','privacy_removal')}>Privacy/removal</a> for a location or personal-information concern.</p><p>Use <a href={route('contribute','bug')}>Bug report</a> for a website problem. It prepares an email draft or links to GitHub. Developers can <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">contribute code on GitHub</a>.</p></section>
  <p><a href={route('database/downloads')}>Downloads</a> · <a href={route('database/api')}>API documentation</a> · <a href={route('about/sources')}>Sources & methodology</a></p>
</section>
<style>
  .help-page{width:min(100% - 3rem,46rem);margin:auto;padding:1.5rem 0 2.5rem;font:.9rem/1.5 system-ui,sans-serif;color:#f1efe8}h1{margin:0 0 1rem;font:500 2rem/1.15 Georgia,serif}h2{margin:0 0 .5rem;font:600 1.1rem/1.3 system-ui}section section{margin:1.5rem 0}p{margin:.6rem 0;color:#c6d0c5}ol{margin:.5rem 0;padding-left:1.2rem;color:#c6d0c5}li{margin:.35rem 0}a{color:#dce8d9;text-underline-offset:.2rem}figure{margin:1rem 0}video{display:block;width:100%;max-height:28rem;background:#141916}figcaption{margin-top:.5rem;color:#bfc9bd;font-size:.8rem}@media(max-width:40rem){.help-page{width:calc(100% - 2rem)}h1{font-size:1.65rem}}
</style>
