/**
 * Checks for the office admin dashboard page.
 *
 * Unlike the owner portal, this page builds most of its form elements at runtime via el(...), so a
 * naive "every referenced id exists in the HTML" check produces false positives -- four of them when
 * this was first written. Ids the script creates are collected and treated as existing.
 *
 * Usage: node admin_check.mjs <admin.html>
 */
import fs from 'node:fs';
const file = process.argv[2];
if (!file) { console.error('usage: admin_check.mjs <admin.html>'); process.exit(2); }
const html = fs.readFileSync(file, 'utf8');
const blocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const js = blocks.join('\n');
if (!js.trim()) { console.error('FAIL: no script found'); process.exit(1); }

let failures = 0;
const check = (label, ok, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${detail ? ' -- ' + detail : ''}`);
  if (!ok) failures++;
};

const staticIds = new Set([...html.matchAll(/id="([^"]+)"/g)].map(m => m[1]));
const runtimeIds = new Set([...js.matchAll(/id:\s*["']([^"']+)["']/g)].map(m => m[1]));
const refs = new Set([...js.matchAll(/(?:getElementById|\$)\(\s*["']([^"']+)["']/g)].map(m => m[1]));
const unresolved = [...refs].filter(r => !staticIds.has(r) && !runtimeIds.has(r));
check(`every referenced element id resolves (${refs.size} refs, ${staticIds.size} static, ${runtimeIds.size} runtime)`,
      unresolved.length === 0, unresolved.join(', '));

try { new Function(js); check('admin script parses', true); }
catch (e) { check('admin script parses', false, e.message); }

// Load it against a DOM stub to catch anything that throws at import time.
const mk = (tag='div') => ({ tag, textContent:'', innerHTML:'', value:'', checked:false, hidden:false, type:'',
  style:{}, dataset:{}, children:[], classList:{add(){},remove(){},toggle(){},contains(){return false;}},
  appendChild(c){ this.children.push(c); return c; }, prepend(c){ this.children.unshift(c); return c; },
  removeChild(){}, setAttribute(){}, getAttribute(){return null;}, remove(){}, append(){}, focus(){},
  addEventListener(){}, removeEventListener(){}, querySelector(){ return mk(); }, querySelectorAll(){ return []; },
  contains(){ return false; }, get firstChild(){ return this.children[0] ?? null; }, reset(){}, submit(){} });
const els = {}; for (const id of [...staticIds, ...runtimeIds]) els[id] = mk();
globalThis.document = { createElement: mk, getElementById: id => els[id] ?? mk(), querySelector: () => mk(),
  querySelectorAll: () => [], addEventListener(){}, body: mk(), documentElement: mk(), readyState:'complete', cookie:'' };
globalThis.window = { addEventListener(){}, location:{ href:'/admin-ui', hash:'', search:'', pathname:'/admin-ui' },
  localStorage:{ getItem:()=>null, setItem(){}, removeItem(){} }, setTimeout, clearTimeout };
globalThis.location = globalThis.window.location; globalThis.localStorage = globalThis.window.localStorage;
globalThis.history = { replaceState(){}, pushState(){} };
globalThis.fetch = async () => ({ ok:true, status:200, json: async()=>({}), text: async()=>'' });
globalThis.confirm = () => true; globalThis.alert = () => {};
try { new Function(js)(); check('admin script loads without throwing', true); }
catch (e) { check('admin script loads without throwing', false, e.constructor.name + ': ' + e.message); }

console.log(failures === 0 ? '\nADMIN UI CHECKS PASSED' : `\nADMIN UI CHECKS FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
