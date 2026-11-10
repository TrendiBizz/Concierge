/**
 * Runtime checks for the customer-facing embeddable widget.
 *
 * Why this exists: the widget is what a customer actually interacts with on a business's site, and
 * nothing verified that it loads. It is a self-contained IIFE that derives its API base from its own
 * script src, so a runtime error takes the assistant down on every site embedding it while the API
 * looks perfectly healthy.
 *
 * Usage: node widget_check.mjs <widget.js>
 */
import fs from 'node:fs';
const file = process.argv[2];
if (!file) { console.error('usage: widget_check.mjs <widget.js>'); process.exit(2); }
const widget = fs.readFileSync(file, 'utf8');

// The widget is an IIFE that returns early without a data-key. Model a realistic host page.
const mk = (tag='div') => ({ tag, textContent:'', innerHTML:'', value:'', style:{}, dataset:{}, children:[],
  classList:{add(){},remove(){},toggle(){},contains(){return false;}},
  appendChild(c){ this.children.push(c); return c; }, prepend(c){ this.children.unshift(c); return c; },
  removeChild(){}, setAttribute(){}, getAttribute(){ return null; }, remove(){},
  addEventListener(){}, removeEventListener(){}, querySelector(){ return mk(); },
  querySelectorAll(){ return []; }, attachShadow(){ return mk(); }, focus(){}, contains(){return false;},
  get firstChild(){ return this.children[0] ?? null; } });

const scriptEl = mk('script');
scriptEl.getAttribute = (n) => (n === 'data-key' ? 'pk_test_key_1234567890' : null);
scriptEl.src = 'https://chat.trendibizz.com/widget.js';
scriptEl.remove = () => {};

globalThis.document = {
  currentScript: scriptEl,
  createElement: mk, getElementById: () => null, querySelector: () => null,
  querySelectorAll: () => [], addEventListener(){}, removeEventListener(){},
  body: mk(), head: mk(), documentElement: mk(), readyState:'complete', cookie:'',
};
globalThis.window = { addEventListener(){}, removeEventListener(){}, location:{ href:'https://client.example.com/', origin:'https://client.example.com' },
  localStorage:{ getItem:()=>null, setItem(){}, removeItem(){} }, setTimeout, clearTimeout, setInterval, clearInterval,
  matchMedia: () => ({ matches:false, addEventListener(){} }), innerWidth:1280, innerHeight:800 };
globalThis.location = globalThis.window.location;
// `navigator` is a getter-only global in modern Node, so define it rather than assign.
Object.defineProperty(globalThis, 'navigator', { configurable:true, value: { userAgent:'node', mediaDevices:{ getUserMedia: async () => { throw new Error('no mic in test'); } } } });
globalThis.fetch = async () => ({ ok:true, status:200, json: async()=>({ name:'Test', greeting:'Hi', voice_enabled:false, accent_color:'#000', cta_text:'x' }), text: async()=>'' });
globalThis.WebSocket = class { constructor(){ this.readyState=1; } addEventListener(){} send(){} close(){} };
globalThis.AudioContext = class { constructor(){ this.destination={}; this.sampleRate=24000; } createMediaStreamSource(){return{connect(){}};} createScriptProcessor(){return{connect(){},onaudioprocess:null};} createAnalyser(){return{connect(){},fftSize:256};} createGain(){return{connect(){},gain:{value:1}};} resume(){} close(){} };
globalThis.URL = URL;

let failed = 0;
try {
  new Function(widget)();
  console.log('ok   widget loads without throwing');
} catch (e) {
  console.log('FAIL widget threw at load:', e.constructor.name + ':', e.message);
  failed++;
}

if (globalThis.window.__ccWidgetLoaded) {
  console.log('ok   widget registered itself (__ccWidgetLoaded set)');
} else {
  console.log('FAIL widget did not register');
  failed++;
}
console.log(failed === 0 ? '\nWIDGET CHECKS PASSED' : `\nWIDGET CHECKS FAILED (${failed})`);
process.exit(failed === 0 ? 0 : 1);
