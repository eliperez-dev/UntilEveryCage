import type { Location } from '../domain/location';
export type DisplayFeature=Readonly<{id:string,label:string,lat:number,lon:number}>;
export const projectLocations=(items:readonly Location[]):readonly DisplayFeature[]=>items.flatMap((item)=>item.lat===null||item.lon===null?[]:[{id:item.id,label:item.name,lat:item.lat,lon:item.lon}]);
