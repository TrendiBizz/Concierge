// Execute the real widget with an in-memory DOM and a stubbed configuration fetch.
// No browser session, network, LLM, microphone or paid provider is used.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
test('host open event displays the assistant without starting chat or voice',async()=>{
  const elements=[];
  function element(tag){
    const values=new Set();
    const item={tag,attrs:{},children:[],style:{},listeners:{},scrollHeight:0,
      setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return this.attrs[k]??null;},
      appendChild(child){this.children.push(child);return child;},
      addEventListener(k,fn){this.listeners[k]=fn;},
      focus(){this.focused=true;},
      classList:{add:v=>values.add(v),remove:v=>values.delete(v),contains:v=>values.has(v)},
      attachShadow(){this.shadowRoot=element('shadow');return this.shadowRoot;}
    };elements.push(item);return item;
  }
  const script=element('script');script.src='https://chat.trendibizz.com/widget.js';
  script.setAttribute('data-key','pk_synthetic_only');
  const body=element('body'),window=new EventTarget(),requests=[];
  window.crypto=webcrypto;
  let ready=0;window.addEventListener('concierge:ready',()=>ready++);
  vm.runInNewContext(fs.readFileSync('api/static/widget.js','utf8'),{
    window,Event,URL,URLSearchParams,crypto:webcrypto,navigator:{},
    location:{href:'https://trendibizz.com/',search:''},
    localStorage:{getItem(){return null;},setItem(){}},
    document:{currentScript:script,body,createElement:element,createTextNode:text=>({textContent:text})},
    fetch:async url=>{requests.push(url);return {ok:true,json:async()=>({name:'Concierge',greeting:'Synthetic greeting',cta_text:'Ask Concierge',voice_enabled:false})};}
  });
  await new Promise(setImmediate);
  assert.equal(ready,1);assert.equal(window.__ccWidgetReady,true);
  const panel=elements.find(el=>el.className==='panel');
  assert.ok(panel);assert.equal(panel.classList.contains('open'),false);
  window.dispatchEvent(new Event('concierge:open'));
  assert.equal(panel.classList.contains('open'),true);
  assert.equal(requests.length,1);
  assert.match(requests[0],/\/api\/v1\/widget-config\?key=pk_synthetic_only$/);
  const input=elements.find(el=>el.attrs['aria-label']==='Message');
  assert.equal(input.focused,true);
});
