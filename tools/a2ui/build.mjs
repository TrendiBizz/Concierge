import {build} from 'esbuild';
const result=await build({entryPoints:['renderer.js'], bundle:true, minify:true, format:'iife', target:'es2022',
  outfile:'../../api/static/a2ui-renderer.js', legalComments:'eof',metafile:true});
console.log('PASS official Lit renderer built');
