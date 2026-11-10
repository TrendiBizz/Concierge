/**
 * Static and runtime checks for the served owner portal page.
 *
 * Why this exists: the portal is a single 62 KB inline script. Nothing verified that it parses, that
 * every element id it references exists, or that it loads without throwing. A typo in one handler
 * would take the whole page down and every API-level test would still pass.
 *
 * Usage: node owner_ui_check.mjs <path-to-owner.html>
 */
import fs from 'node:fs';

const file = process.argv[2];
if (!file) { console.error('usage: owner_ui_check.mjs <owner.html>'); process.exit(2); }
const html = fs.readFileSync(file, 'utf8');
const blocks = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const app = blocks.find(b => b.includes('sessionGeneration')) || blocks[0];
if (!app) { console.error('FAIL: no application script block found'); process.exit(1); }

let failures = 0;
const check = (label, ok, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${detail ? ' -- ' + detail : ''}`);
  if (!ok) failures++;
};

// 1. Every element id the script looks up must exist in the markup.
const ids = new Set([...html.matchAll(/id="([^"]+)"/g)].map(m => m[1]));
const refs = new Set([...app.matchAll(/\$\("([^"]+)"\)/g)].map(m => m[1]));
const dangling = [...refs].filter(r => !ids.has(r));
check('every referenced element id exists', dangling.length === 0, dangling.join(', '));

// 2. The script must parse.
try { new Function(app); check('application script parses', true); }
catch (e) { check('application script parses', false, e.message); }

// 3. It must load without throwing, against a DOM stub of every declared id.
const mk = (tag = 'div') => ({ tag, textContent:'', value:'', checked:false, disabled:false, hidden:false,
  type:'', style:{}, dataset:{}, children:[], classList:{add(){},remove(){},toggle(){}},
  appendChild(c){ this.children.push(c); return c; }, prepend(c){ this.children.unshift(c); return c; },
  removeChild(){}, setAttribute(){}, getAttribute(){return null;}, addEventListener(){},
  removeEventListener(){}, querySelector(){ return mk(); }, querySelectorAll(){ return []; },
  focus(){}, remove(){}, insertBefore(){}, contains(){ return false; },
  get firstChild(){ return this.children[0] ?? null; }, reset(){}, submit(){}, checkValidity(){ return true; } });
const els = {}; for (const id of ids) els[id] = mk();
globalThis.document = { createElement: mk, getElementById: id => els[id] ?? null, querySelector: () => mk(),
  querySelectorAll: () => [], addEventListener(){}, body: mk(), documentElement: mk(), readyState:'complete', cookie:'' };
globalThis.window = { addEventListener(){}, location:{ href:'/owner-ui', hash:'', search:'', pathname:'/owner-ui' },
  localStorage:{ getItem:()=>null, setItem(){}, removeItem(){} }, setTimeout, clearTimeout };
globalThis.location = globalThis.window.location;
globalThis.localStorage = globalThis.window.localStorage;
globalThis.history = { replaceState(){}, pushState(){} };
globalThis.fetch = async () => ({ ok:false, status:401, json: async()=>({}), text: async()=>'' });
globalThis.confirm = () => true; globalThis.alert = () => {};
globalThis.EventSource = class { constructor(){ this.addEventListener = () => {}; } close(){} };

const wanted = ['refresh','refreshCRM','refreshOnboarding','refreshQuotes','refreshCalendar',
  'refreshChannelAuthorizations','refreshKnowledge','refreshEmailJobs','refreshSocial','message'];
try {
  const scope = new Function(app + `\n; return { ${wanted
    .map(n => `${n}: typeof ${n}!=='undefined'?${n}:null`).join(', ')} };`)();
  const missing = wanted.filter(n => typeof scope[n] !== 'function');
  check('application script loads without throwing', true);
  check('all portal refresh functions are defined', missing.length === 0, missing.join(', '));
} catch (e) {
  check('application script loads without throwing', false, e.constructor.name + ': ' + e.message);
}

console.log(failures === 0 ? '\nOWNER UI CHECKS PASSED' : `\nOWNER UI CHECKS FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
