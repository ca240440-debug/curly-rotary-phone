const {cpSync, writeFileSync, readFileSync, rmSync} = require('node:fs');
const {resolve} = require('node:path');
const root = resolve(__dirname, '..');
const scaffold = process.argv.includes('--scaffold');
let base = '';
if (!scaffold) {
  if (!process.env.WISHNEST_API_BASE) throw Error('Set WISHNEST_API_BASE to your deployed HTTPS backend, or use mobile:scaffold for nonfunctional platform scaffolds.');
  const url = new URL(process.env.WISHNEST_API_BASE);
  if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw Error('WISHNEST_API_BASE must be an HTTPS origin without credentials, path, or query.');
  base = url.origin;
}
rmSync(resolve(root,'dist'),{recursive:true,force:true});
cpSync(resolve(root,'public'),resolve(root,'dist'),{recursive:true});
writeFileSync(resolve(root,'dist/runtime.js'), 'window.WISHNEST_API_BASE = '+JSON.stringify(base)+';\nwindow.WISHNEST_NATIVE_BUILD = true;\nwindow.WISHNEST_NATIVE_SCAFFOLD = '+JSON.stringify(scaffold)+';\n');
const csp = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self' " + base + "; base-uri 'none'; form-action 'self'";
let html = readFileSync(resolve(root,'dist/index.html'),'utf8');
html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="'+csp+'">');
writeFileSync(resolve(root,'dist/index.html'), html);
console.log(scaffold ? 'Native scaffold assets generated. Backend is intentionally unconfigured; not a release build.' : 'Native assets generated for '+base+'. Configure the backend origin allowlist and sync platforms next.');
