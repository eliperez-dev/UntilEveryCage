<script lang="ts">
  let { section = 'overview', returnMapHref = '#/map' }: { section: 'overview' | 'manifesto'; returnMapHref?: string } = $props();
  const context = $derived(returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : '');
</script>
<svelte:head><title>{section === 'overview' ? 'About' : 'Manifesto'} · Until Every Cage</title></svelte:head>
<section class="about-page" aria-label="About Until Every Cage">
  {#if section === 'overview'}
    <h1>About Until Every Cage</h1>
    <p>Until Every Cage maps documented animal-agriculture facilities and brings the sources behind each record into view.</p>
    <p>We make the infrastructure of animal exploitation easier to investigate, in service of animal liberation. Researchers, journalists, and advocates can explore the map, search the database, and inspect the evidence.</p>
    <p><a href={`#/about/manifesto${context}`}>Manifesto</a> · <a href={`#/about/sources${context}`}>Sources & methodology</a></p>
  {:else}
    <h1>Make the hidden visible.</h1>
    <p>What is hidden is easier to ignore. We expose the places and systems behind animal exploitation so people can investigate, understand, and act.</p>
    <p>We stand for animal liberation and open research. Our sources remain inspectable, our interpretations stay distinct from their evidence, and gaps stay visible.</p>
    <p class="manifesto-close">Until every cage is empty.</p>
    <p><a href={`#/about/sources${context}`}>Sources & methodology</a></p>
  {/if}
</section>
<style>
  .about-page{width:min(100% - 3rem,46rem);margin:auto;padding:1.5rem 0 2.5rem;color:#f1efe8;font:.94rem/1.5 system-ui,sans-serif}
  h1{margin:0 0 1rem;font:500 2rem/1.15 Georgia,serif;letter-spacing:-.02em}p{margin:0 0 1rem;color:#c6d0c5}a{color:#dce8d9;text-underline-offset:.2em}.manifesto-close{font-style:italic;color:#eee4ce}
  @media(max-width:40rem){.about-page{width:calc(100% - 2rem)}h1{font-size:1.65rem}}
</style>
