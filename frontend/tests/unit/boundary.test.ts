import {describe,expect,it} from 'vitest'; import {readFileSync} from 'node:fs'; import {resolve} from 'node:path';
describe('V1 boundary',()=>it('keeps V2 output isolated from static/',()=>{const config=readFileSync(resolve(process.cwd(),'vite.config.ts'),'utf8');expect(config).toMatch(/outDir:\s*'dist'/);expect(config).not.toMatch(/outDir:\s*'\.\.\/static'/);}));
