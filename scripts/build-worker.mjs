import {readFile,writeFile,mkdir,readdir} from 'node:fs/promises';
import path from 'node:path';
const assets={};const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.txt':'text/plain','.zip':'application/zip'};
async function walk(dir){for(const item of await readdir(dir,{withFileTypes:true})){if(item.name==='server')continue;const p=path.join(dir,item.name);if(item.isDirectory())await walk(p);else assets['/'+path.relative('dist',p)]={type:types[path.extname(p)]||'application/octet-stream',data:(await readFile(p)).toString('base64')}}}
await walk('dist');await mkdir('worker',{recursive:true});await writeFile('worker/assets.js','export const ASSETS='+JSON.stringify(assets)+';\n');
