import type { Location } from '../../domain/location';
import { taxonomyMatchesFilters, taxonomySearchText, type TaxonomyPrimaryKey } from '../../domain/taxonomy';
export type FilterState=Readonly<{search:string;region:string;category:string;categories?:readonly TaxonomyPrimaryKey[];source?:string}>;
export const initialFilters:FilterState={search:'',region:'all',category:'all'};
export const filterLocations=(items:readonly Location[],filters:FilterState):readonly Location[]=>{
  const needle=filters.search.trim().toLocaleLowerCase();
  const selectedCategories=filters.categories??[];
  return items.filter(item=>{
    const activityText=taxonomySearchText(item.taxonomy).toLocaleLowerCase();
    const searchable=`${item.name} ${item.region} ${item.category} ${activityText}`.toLocaleLowerCase();
    const legacyCategoryMatches=filters.category==='all'||item.category===filters.category;
    const taxonomyMatches=taxonomyMatchesFilters(item,selectedCategories,filters.source&&filters.source!=='all'?filters.source:null);
    return (!needle||searchable.includes(needle))&&(filters.region==='all'||item.region===filters.region)&&legacyCategoryMatches&&taxonomyMatches;
  });
};
