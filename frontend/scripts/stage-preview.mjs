import { cp, mkdir, rm, realpath } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
const root=resolve(import.meta.dirname,'..','..'); const source=resolve(root,'frontend','dist'); const destination=resolve(root,'static','v2-preview');
const safeRoot=resolve(root,'static'); if (!destination.startsWith(safeRoot+sep)) throw new Error('Unsafe staging destination');
await realpath(source); await mkdir(safeRoot,{recursive:true}); await rm(destination,{recursive:true,force:true}); await cp(source,destination,{recursive:true}); console.log(`Staged V2 preview at ${destination}`);
