import type { ExportModel } from './exportModel';
export const previewExport=(model:ExportModel):string=>JSON.stringify({context:{profile:model.profile,release:model.release,limitations:model.limitations},rows:model.rows.map((row)=>({id:row.id,name:row.name,source:row.source,observed:row.observed}))},null,2);
