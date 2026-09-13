import type { Location } from '../domain/location'; import type { Profile } from '../domain/publication';
export type ExportModel=Readonly<{profile:Profile;release:string;limitations:readonly string[];rows:readonly Location[]}>;
export const makeExportModel=(rows:readonly Location[],profile:Profile,release='synthetic-2026.09'):ExportModel=>({profile,release,limitations:['Synthetic fixture only','Not a live database export','Coordinates may be unavailable'],rows});
