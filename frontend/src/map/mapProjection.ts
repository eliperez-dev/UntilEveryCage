import type { Location } from '../domain/location';
export type DisplayFeature=Readonly<{id:string,label:string,lat:number,lon:number,precision:'exact'|'city'}>;
export type DisplayCluster=Readonly<{id:string,label:string,lat:number,lon:number,count:number,memberIds:readonly string[]}>;
export type MapDisplayItem=DisplayFeature|DisplayCluster;
export const projectLocations=(items:readonly Location[]):readonly DisplayFeature[]=>items.flatMap((item)=>item.lat===null||item.lon===null?[]:[{id:item.id,label:item.evidence?.publicationProfile==='community'&&item.evidence.factualReviewStatus==='unreviewed'?`${item.name} · Unreviewed community claim — not verified by Until Every Cage`:item.name,lat:item.lat,lon:item.lon,precision:item.evidence?.displayPrecision==='exact'?'exact':'city'}]);

/**
 * Cluster only the already release-filtered page received by the client. The
 * result is intentionally not a count of the dataset: it is a rendering aid
 * for the current response page, and the UI says so beside the map.
 */
export const clusterFeatures=(features:readonly DisplayFeature[], cellSize=0.5):readonly MapDisplayItem[]=>{
  const cells=new Map<string,DisplayFeature[]>();
  for(const feature of features){const key=`${Math.floor(feature.lat/cellSize)}:${Math.floor(feature.lon/cellSize)}`;const cell=cells.get(key)??[];cell.push(feature);cells.set(key,cell);}
  const display:MapDisplayItem[]=[];
  for(const [key,members] of cells){
    if(members.length===1){display.push(members[0]!);continue;}
    const lat=members.reduce((sum,item)=>sum+item.lat,0)/members.length;
    const lon=members.reduce((sum,item)=>sum+item.lon,0)/members.length;
    display.push({id:`cluster:${key}`,label:`${members.length} facility records in this map cluster`,lat,lon,count:members.length,memberIds:members.map(item=>item.id)});
  }
  return display;
};
