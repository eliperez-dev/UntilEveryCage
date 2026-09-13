<script lang="ts">
  export let profile: string;
  export let releaseId: string;
  export let ruleset: string | undefined = undefined;
  export let manifestSha256: string | undefined = undefined;
</script>

<section class="release-panel" aria-label="Release and provenance context">
  <div><span>PROFILE</span><strong>{profile}</strong></div>
  <div><span>RELEASE</span><strong>{releaseId}</strong></div>
  {#if ruleset}<div><span>RULESET</span><strong>{ruleset}</strong></div>{/if}
  {#if manifestSha256}<div><span>MANIFEST DIGEST</span><strong class="digest">{manifestSha256}</strong></div>{/if}
  <p>Release context supports traceability and integrity checks; it is not human approval or cryptographic signing.</p>
</section>
