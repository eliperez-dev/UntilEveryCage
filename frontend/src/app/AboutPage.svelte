<script lang="ts">
  import AboutSubnav from './AboutSubnav.svelte';
  let { section = 'overview', returnMapHref = '#/map' }: { section: 'overview' | 'manifesto'; returnMapHref?: string } = $props();
</script>

<svelte:head><title>{section === 'overview' ? 'About' : 'Manifesto'} · Until Every Cage</title></svelte:head>
<section class="about-page" aria-label="About Until Every Cage">
  <AboutSubnav current={section} {returnMapHref} />
  {#if section === 'overview'}
    <header class="intro"><h1>About Until Every Cage</h1><p class="lede">Until Every Cage is a public research project that maps documented animal-agriculture facilities and makes the evidence behind each record easier to inspect.</p></header>
    <section class="overview-copy"><h2>Why make a map?</h2><p>Animal agriculture is supported by places and organizations that can remain difficult to see. We bring public documentation into a searchable view so people can ask better questions about what is known, where it came from, and what remains uncertain.</p><p>Our purpose is to make this infrastructure more visible in service of animal liberation. Careful research can support that work when evidence is traceable, limits are plain, and a map point is not mistaken for proof of every claim about a place.</p><a class="read-more" href={`#/about/manifesto${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`}>Read the manifesto <span aria-hidden="true">→</span></a></section>
  {:else}
    <header class="intro manifesto-intro"><h1>Make the hidden visible.</h1><p class="lede">Transparency is part of animal liberation. We work to expose the places and systems that support animal exploitation, and to make the records behind that work open to scrutiny.</p></header>
    <section class="manifesto-copy"><p>Until Every Cage exists because what is hidden is easier to ignore. Public documentation can help reveal how this industry is organized and give researchers, journalists, and advocates a place to begin asking questions.</p><p>We take a clear position against animal exploitation. We also hold our own claims to a standard of evidence: source statements stay distinct from interpretation, missing information is not filled in by guesswork, and uncertainty remains visible.</p><p>Visibility is not the same as proof. A facility record does not establish every activity, current operation, or wrongdoing. The work is to show what the evidence supports, to say what it does not, and to keep people’s privacy and safety in view.</p><p class="manifesto-close">Until every cage is empty.</p><a class="read-more" href={`#/about/sources${returnMapHref !== '#/map' ? `?map=${encodeURIComponent(returnMapHref)}` : ''}`}>Read sources & methodology <span aria-hidden="true">→</span></a></section>
  {/if}
</section>

<style>
  .about-page{width:min(100% - 3rem,72rem);margin:auto;padding:clamp(2rem,5vw,4rem) 0 6rem;color:#f1efe8;font:1rem/1.7 ui-sans-serif,system-ui,sans-serif}.intro{max-width:49rem;padding:2.6rem 0 2.4rem;border-bottom:1px solid #485149}.about-page h1{margin:.3rem 0 1rem;font:400 clamp(2.6rem,6.5vw,4.8rem)/1.05 Georgia,serif;letter-spacing:-.04em}.lede{max-width:45rem;margin:0;color:#d3dbd1;font-size:clamp(1.05rem,1.55vw,1.25rem)}.overview-copy,.manifesto-copy{max-width:48rem;padding:2.2rem 0}.about-page h2{font:400 clamp(1.7rem,3vw,2.3rem)/1.2 Georgia,serif}.overview-copy p,.manifesto-copy p{color:#c6d0c5}.read-more{display:inline-flex;gap:.6rem;margin-top:.6rem;color:#dce8d9;text-underline-offset:.25em}.manifesto-intro{padding-bottom:2.8rem}.manifesto-copy{padding-top:1.5rem}.manifesto-close{margin-top:2rem;font:italic 1.25rem Georgia,serif;color:#eee4ce!important}.about-page a:focus-visible{outline:2px solid #f1efe8;outline-offset:3px}@media(max-width:44rem){.about-page{width:min(100% - 2rem,72rem)}.intro{padding-top:2rem}}
</style>
