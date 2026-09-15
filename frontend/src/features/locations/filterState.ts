import type { Location } from '../../domain/location';
export type FilterState=Readonly<{search:string;region:string;category:string}>;
export const initialFilters:FilterState={search:'',region:'all',category:'all'};
export const filterLocations=(items:readonly Location[],filters:FilterState):readonly Location[]=>{const needle=filters.search.trim().toLocaleLowerCase();return items.filter((item)=>(!needle||`${item.name} ${item.region} ${item.category}`.toLocaleLowerCase().includes(needle))&&(filters.region==='all'||item.region===filters.region)&&(filters.category==='all'||item.category===filters.category));};
