import { readFileSync, readdirSync, statSync } from 'node:fs'; import { resolve } from 'node:path';
const root=resolve(import.meta.dirname,'..'); const dist=resolve(root,'dist');
const walk=p=>readdirSync(p).flatMap(n=>{const f=resolve(p,n);return statSync(f).isDirectory()?walk(f):[f]});
const forbidden=['F1A_SYNTHETIC_REVIEW_ONLY','Synthetic Poultry record'];
for(const file of walk(dist)){const body=readFileSync(file,'utf8');for(const marker of forbidden)if(body.includes(marker))throw new Error(`production output leaked design-lab marker ${marker}: ${file}`)}
console.log('Design-lab fixtures and sentinels are absent from production output.');
