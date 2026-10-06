<script lang="ts">
  let { returnMapHref = '#/map', embedded = false }: { returnMapHref?: string; embedded?: boolean } = $props();
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
<section class="bug-page" class:embedded aria-label="Report a bug">
  {#if !embedded}<p><a href={`#/contribute${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`}>Contribute</a></p>
  <h1>Report a bug</h1>{/if}
  <p class="intro">Prepare an email draft or report the issue on GitHub.</p>
  <form class="bug-form" onsubmit={prepareEmail}>
    <label>What happened?<textarea name="happened" required maxlength="2000" rows="2"></textarea></label>
    <label>What did you expect?<textarea name="expected" maxlength="1000" rows="2"></textarea></label>
    <label>Steps to reproduce<textarea name="steps" required maxlength="2000" rows="2"></textarea></label>
    <label>Page link (optional)<input name="page_url" type="url" maxlength="1000" placeholder="https://…" /></label>
    <button type="submit">Prepare email</button>
  </form>
  {#if emailHref}<p class="draft-link"><a href={emailHref}>Open email draft</a></p>{/if}
  <p class="issue-link"><a href="https://github.com/eliperez-dev/UntilEveryCage/issues/new" target="_blank" rel="noreferrer">Report a public issue on GitHub ↗</a></p>
</section>

<style>
  .bug-page{width:min(100% - 3rem,48rem);margin:0 auto;padding:1.5rem 0 2.5rem;color:#f1efe8;font:.9rem/1.5 ui-sans-serif,system-ui,sans-serif}.bug-page a{color:#dce8d9;text-underline-offset:.25em}.bug-page h1{margin:.4rem 0 .75rem;font:400 clamp(1.65rem,4vw,2rem)/1.08 Georgia,serif;letter-spacing:-.035em}.intro{max-width:42rem;color:#d3dbd1;font-size:.9rem}.bug-form{display:grid;gap:.75rem;margin-top:.75rem}.bug-form label{display:grid;gap:.4rem;color:#e6e2d8;font-size:.9rem}.bug-form textarea,.bug-form input{width:100%;padding:.45rem .6rem;border:1px solid #59615c;border-radius:2px;background:#202523;color:#f4f1e9;font:inherit}.bug-form textarea{resize:vertical}.bug-form :focus-visible{outline:3px solid #d49a62;outline-offset:2px}.bug-form button{width:max-content;min-height:2.5rem;padding:.55rem 1rem;border:1px solid #c58a58;border-radius:2px;background:#8f553d;color:#fff;font:600 .9rem system-ui;cursor:pointer}.draft-link,.issue-link{margin-top:1.3rem}.draft-link a{display:inline-flex;padding:.7rem .9rem;border:1px solid #9a7556;background:#262b27}.issue-link{color:#bec8bf;font-size:.88rem}@media(max-width:40rem){.bug-page{width:min(100% - 2rem,48rem)}}
.bug-page.embedded{width:100%;margin:0;padding:0}
</style>
