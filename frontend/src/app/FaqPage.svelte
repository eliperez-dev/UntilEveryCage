<script lang="ts">
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  const href = (path: string) => `#/${path}${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`;
</script>
<svelte:head><title>FAQ · Until Every Cage</title></svelte:head>
<section class="faq-page" aria-labelledby="faq-title">
  <h1 id="faq-title">FAQ</h1>
  <h2>What does the website show?</h2><p>Source-backed records of facilities and industry activity. Curated releases and community submissions are separate. See <a href={href('about/sources')}>sources & methodology</a> for coverage and limitations.</p>
  <h2>Why is a facility missing?</h2><p>Coverage is incomplete. Missing records do not establish that a facility does not exist or has closed.</p>
  <h2>How accurate are the locations?</h2><p>Read each record’s location precision. City-level locations are approximations; unmapped records have no publishable point.</p>
  <h2>How can I add or correct a record?</h2><p>Use <a href={href('contribute')}>Contribute</a> to add a facility, evidence, a correction, or a privacy/removal request. Existing-record requests need its record link or ID.</p>
  <h2>Does submitting publish my contribution?</h2><p>No. Submissions enter private review and do not automatically change published records.</p>
  <h2>How do I check its progress?</h2><p>Save the Submission ID and private receipt shown after sending, then use <a href={href('contribution-status')}>Check status</a>. A Submission ID identifies your contribution; a Record ID identifies an existing facility. Automatic email updates are not available yet.</p>
  <h2>Can I download and reuse the data?</h2><p><a href={href('database/downloads')}>Downloads</a> lists the public exports and reuse terms. The compilation’s CC BY-NC-SA 4.0 license limits commercial reuse; source and provider terms also apply.</p>
  <h2>Can I help with the code?</h2><p>Yes. The code is open source under AGPLv3 or later. Contribute code, tests, design, or data adapters on <a href="https://github.com/eliperez-dev/UntilEveryCage" target="_blank" rel="noreferrer">GitHub</a>.</p>
  <p class="more">For step-by-step instructions, visit <a href={href('about/help')}>Help</a>.</p>
</section>
<style>
  .faq-page{width:min(100% - 3rem,46rem);margin:auto;padding:1.5rem 0 2rem;color:#f1efe8;font:.9rem/1.5 system-ui,sans-serif}h1{margin:0 0 1rem;font:500 2rem/1.15 Georgia,serif}h2{margin:1.25rem 0 .35rem;font:600 1rem/1.4 system-ui,sans-serif}p{margin:0;color:#c6d0c5}.more{margin-top:1.5rem}a{color:#dce8d9;text-underline-offset:.2em}a:focus-visible{outline:2px solid #eee7d6;outline-offset:3px}@media(max-width:40rem){.faq-page{width:calc(100% - 2rem)}h1{font-size:1.65rem}}
</style>
