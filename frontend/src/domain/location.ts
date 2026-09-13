export type LocationId = `syn-${string}`;
export type Location = Readonly<{id:LocationId,name:string,region:string,category:string,lat:number|null,lon:number|null,observed:string,source:string}>;
