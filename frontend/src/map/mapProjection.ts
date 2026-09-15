import type { Location } from '../domain/location';
export type DisplayFeature=Readonly<{id:string,label:string,lat:number,lon:number}>;
export const projectLocations=(items:readonly Location[]):readonly DisplayFeature[]=>items.flatMap((item)=>item.lat===null||item.lon===null?[]:[{id:item.id,label:item.evidence?.publicationProfile==='community'&&item.evidence.factualReviewStatus==='unreviewed'?`${item.name} · Unreviewed community claim — not verified by Until Every Cage`:item.name,lat:item.lat,lon:item.lon}]);
