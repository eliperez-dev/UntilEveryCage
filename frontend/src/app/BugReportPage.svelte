<script lang="ts">
  let { returnMapHref = '#/map' }: { returnMapHref?: string } = $props();
  let emailHref = $state('');

  function prepareEmail(event: SubmitEvent) {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const values = new FormData(form);
    const report = [
      `What happened:\n${String(values.get('happened') ?? '').trim()}`,
      `What did you expect?\n${String(values.get('expected') ?? '').trim() || 'Not provided'}`,
      `Steps to reproduce:\n${String(values.get('steps') ?? '').trim()}`,
      `Page link (optional):\n${String(values.get('page_url') ?? '').trim() || 'Not provided'}`,
    ].join('\n\n');
    emailHref = `mailto:untileverycageproject@protonmail.com?subject=${encodeURIComponent('Website bug report')}&body=${encodeURIComponent(report)}`;
  }
</script>

<svelte:head><title>Report a bug · Until Every Cage</title></svelte:head>
<section class="bug-page" aria-label="Report a bug">
  <p><a href={`#/contribute${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`}>Contribute</a></p>
  <h1>Report a bug</h1>
  <p class="intro">Describe what happened so we can try to reproduce it. This page prepares an email draft; it does not send anything.</p>
  <p class="privacy-note">Use email for private details. GitHub issues are public. Don’t include credentials, private search text, or personal information in a page link.</p>
  <form class="bug-form" onsubmit={prepareEmail}>
    <label>What happened?<textarea name="happened" required maxlength="2000" rows="4"></textarea></label>
    <label>What did you expect?<textarea name="expected" maxlength="1000" rows="3"></textarea></label>
    <label>Steps to reproduce<textarea name="steps" required maxlength="2000" rows="4"></textarea></label>
    <label>Page link (optional; enter it yourself)<input name="page_url" type="url" maxlength="1000" placeholder="https://…" /></label>
    <button type="submit">Prepare email</button>
  </form>
  {#if emailHref}<p class="draft-link"><a href={emailHref}>Open email draft</a></p>{/if}
  <p class="issue-link"><a href="https://github.com/eliperez-dev/UntilEveryCage/issues/new" target="_blank" rel="noreferrer">Report a public issue on GitHub ↗</a></p>
</section>

<style>
  .bug-page{width:min(100% - 3rem,48rem);margin:0 auto;padding:clamp(2rem,6vw,4.5rem) 0 6rem;color:#f1efe8;font:1rem/1.6 ui-sans-serif,system-ui,sans-serif}.bug-page a{color:#dce8d9;text-underline-offset:.25em}.bug-page h1{margin:.4rem 0 .75rem;font:400 clamp(2.5rem,6vw,4rem)/1.08 Georgia,serif;letter-spacing:-.035em}.intro{max-width:42rem;color:#d3dbd1;font-size:1.08rem}.privacy-note{margin:1.2rem 0;padding-left:.8rem;border-left:2px solid #9a7556;color:#c6c7be;font-size:.86rem}.bug-form{display:grid;gap:1rem;margin-top:1.6rem}.bug-form label{display:grid;gap:.4rem;color:#e6e2d8;font-size:.9rem}.bug-form textarea,.bug-form input{width:100%;padding:.65rem .72rem;border:1px solid #59615c;border-radius:2px;background:#202523;color:#f4f1e9;font:inherit}.bug-form textarea{resize:vertical}.bug-form :focus-visible{outline:3px solid #d49a62;outline-offset:2px}.bug-form button{width:max-content;min-height:2.8rem;padding:.55rem 1rem;border:1px solid #c58a58;border-radius:2px;background:#8f553d;color:#fff;font:600 .9rem system-ui;cursor:pointer}.draft-link,.issue-link{margin-top:1.3rem}.draft-link a{display:inline-flex;padding:.7rem .9rem;border:1px solid #9a7556;background:#262b27}.issue-link{color:#bec8bf;font-size:.88rem}@media(max-width:40rem){.bug-page{width:min(100% - 2rem,48rem)}}
</style>
