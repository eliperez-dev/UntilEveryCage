<script lang="ts">
  import { tick } from 'svelte';
  import type { SearchScope } from '../../design-lab/contract';
  import { CATEGORY_PRESENTATIONS } from '../locations/categoryPresentation';
  import { language,tr } from '../../app/language';
  let { scope, categories, scopeLabel, searchMode, radiusMiles, ready, onclear, onarea, onnear, onsettings, oncategories }: {
    scope:SearchScope; categories:readonly string[];scopeLabel:string;searchMode:'box'|'radius';radiusMiles:number;ready:boolean;
    onclear():void;onarea():void;onnear():void;onsettings(value:{mode:'box'|'radius';radiusMiles:number}):void;oncategories():void;
  }=$props();
  let open=$state(false);let button:HTMLButtonElement;let host:HTMLDivElement;
  const names:Record<string,string>={slaughter:'Slaughter',animal_keeping_and_production:'Animal keeping',processing_and_preparation:'Processing',research_and_animal_use:'Research',other_regulated_premises:'Other premises',unclassified:'Unclassified'};
  const categoryLabel=$derived(categories.length===1?tr(names[categories[0]!]??categories[0]!,$language):tr('{count} activities',$language).replace('{count}',new Intl.NumberFormat($language).format(categories.length)));
  const color=$derived(categories.length===1&&categories[0]! in CATEGORY_PRESENTATIONS?CATEGORY_PRESENTATIONS[categories[0] as keyof typeof CATEGORY_PRESENTATIONS].color:'var(--muted)');
  function fitMenu(node:HTMLElement){
    function position(){
      const context=node.parentElement;
      if(!node.isConnected||!context)return;
      const viewport=window.visualViewport;
      const top=viewport?.offsetTop??0;
      const bottom=top+(viewport?.height??window.innerHeight);
      const bounds=context.getBoundingClientRect();
      const floor=Math.max(top,context.closest('.workspace')?.getBoundingClientRect().top??top)+8;
      const below=bottom-bounds.bottom-12;
      const above=bounds.top-floor-8;
      const placement=below<256&&above>below?'above':'below';
      node.style.top=placement==='above'?'auto':'calc(100% - 1px)';
      node.style.bottom=placement==='above'?'calc(100% - 1px)':'auto';
      node.style.setProperty('--scope-menu-available',String(Math.max(44,placement==='above'?above:below))+'px');
    }
    const observer=new ResizeObserver(position);
    void tick().then(()=>{if(node.isConnected&&node.parentElement){position();observer.observe(node.parentElement);}});
    window.addEventListener('resize',position);
    window.visualViewport?.addEventListener('resize',position);
    window.visualViewport?.addEventListener('scroll',position);
    return {destroy(){observer.disconnect();window.removeEventListener('resize',position);window.visualViewport?.removeEventListener('resize',position);window.visualViewport?.removeEventListener('scroll',position);}};
  }
  async function toggle(){open=!open;if(open){await tick();host.querySelector<HTMLButtonElement>('.mobile-scope-menu button')?.focus({preventScroll:true});}}
  function choose(action:()=>void){open=false;action();void tick().then(()=>button.focus({preventScroll:true}));}
  function escape(event:KeyboardEvent){if(event.key==='Escape'&&open){event.preventDefault();event.stopPropagation();open=false;button.focus();}}
</script>
<svelte:window onkeydown={escape} onpointerdown={event=>{if(open&&event.target instanceof Node&&!host.contains(event.target))open=false;}}/>
<div class="mobile-search-context" bind:this={host}>
  <button class="mobile-scope-toggle" bind:this={button} type="button" aria-label={`${tr('Search area',$language)}: ${scopeLabel}`} aria-expanded={open} aria-controls="mobile-scope-menu" onclick={toggle}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/></svg><span>{scopeLabel}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
  {#if scope}<button class="mobile-clear-scope" type="button" aria-label={tr('Clear map area',$language)} onclick={()=>choose(onclear)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>{/if}
  {#if categories.length}<button class="mobile-category-chip" type="button" aria-label={`${tr('Remove filter',$language)}: ${categoryLabel}`} onclick={()=>choose(oncategories)}><i style:background={color}></i><span>{categoryLabel}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>{/if}
  {#if open}<section use:fitMenu id="mobile-scope-menu" class="mobile-scope-menu" aria-label={tr('Search area',$language)}><button type="button" aria-pressed={!scope} onclick={()=>choose(onclear)}>{tr('Everywhere',$language)}</button><button type="button" disabled={!ready} onclick={()=>choose(onarea)}>{tr('Search this area',$language)}</button><button type="button" disabled={!ready} onclick={()=>choose(onnear)}>{tr('Near me',$language)}<small>{tr('{count} miles',$language).replace('{count}',new Intl.NumberFormat($language).format(radiusMiles))}</small></button><details><summary>{tr('Search settings',$language)}</summary><fieldset><legend class="sr-only">{tr('Search area',$language)}</legend><label><input type="radio" name="mobile-search-mode" checked={searchMode==='box'} onchange={()=>onsettings({mode:'box',radiusMiles})} />{tr('Visible map',$language)}</label><label><input type="radio" name="mobile-search-mode" checked={searchMode==='radius'} onchange={()=>onsettings({mode:'radius',radiusMiles})} />{tr('Radius',$language)}</label></fieldset>{#if searchMode==='radius'}<label class="radius-label" for="mobile-search-radius">{tr('Radius',$language)}<output>{tr('{count} miles',$language).replace('{count}',new Intl.NumberFormat($language).format(radiusMiles))}</output></label><input id="mobile-search-radius" type="range" min="5" max="250" step="5" value={radiusMiles} aria-label={tr('Search radius',$language)} aria-valuetext={tr('{count} miles',$language).replace('{count}',String(radiusMiles))} oninput={event=>onsettings({mode:'radius',radiusMiles:Number(event.currentTarget.value)})}/>{/if}</details></section>{/if}
</div>
<style>
  .mobile-search-context{position:relative;display:flex;align-items:center;gap:.15rem;min-height:44px;padding:0 .75rem;min-width:0;background:var(--panel)}button{display:flex;align-items:center;gap:.35rem;min-height:44px;padding:0;border:0;background:none;color:var(--ink);font:inherit;font-size:.6875rem;cursor:pointer}svg{width:12px;height:12px;flex:none;fill:none;stroke:var(--muted);stroke-width:1.5}.mobile-scope-toggle{flex:0 1 auto;min-width:0}.mobile-scope-toggle>span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.mobile-clear-scope{min-width:44px;justify-content:center}.mobile-category-chip{min-height:44px;max-width:47%;min-width:0;margin-left:auto;padding:.3rem .4rem;border:1px solid var(--line);gap:.35rem}.mobile-category-chip>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.mobile-category-chip i{width:6px;height:6px;border-radius:50%;flex:none}
  .mobile-scope-menu{position:absolute;z-index:15;top:calc(100% - 1px);left:.75rem;right:.75rem;border:1px solid var(--line);background:var(--panel);box-shadow:0 8px 24px #0004;padding:.25rem .65rem;max-height:min(23rem,var(--scope-menu-available,10rem));overflow:auto;overscroll-behavior:contain}.mobile-scope-menu>button{width:100%;justify-content:space-between;text-align:left;font-size:.75rem}.mobile-scope-menu>button[aria-pressed=true]{text-decoration:underline;text-underline-offset:3px}small,output{color:var(--muted);font:inherit}details{border-top:1px solid var(--line)}summary{min-height:44px;display:flex;align-items:center;cursor:pointer;font-size:.75rem}fieldset{border:0;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:.4rem 1rem}label{display:flex;align-items:center;gap:.4rem;min-height:44px;font-size:.75rem}.radius-label{justify-content:space-between}input{accent-color:var(--ink)}input[type=range]{box-sizing:border-box;width:100%;min-height:44px;margin:0}button:disabled{opacity:.4;cursor:default}button:focus-visible,summary:focus-visible,input:focus-visible{outline:2px solid var(--ink);outline-offset:2px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}
</style>
