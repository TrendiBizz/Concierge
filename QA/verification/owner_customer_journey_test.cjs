// Execute real owner-portal JavaScript with in-memory elements and HTTP stubs.
// This is an offline client contract, not browser or provider certification.
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const html=fs.readFileSync('api/static/owner.html','utf8');
function element(){
  const el={children:[],value:'',hidden:false,handlers:{},attrs:{},dataset:{},disabled:false,
    addEventListener(k,fn){this.handlers[k]=fn;},setAttribute(k,v){this.attrs[k]=v;},
    appendChild(child){this.children.push(child);return child;},prepend(child){this.children.unshift(child);},
    removeChild(child){this.children.splice(this.children.indexOf(child),1);},
    querySelector(){return element();},focus(){this.focused=true;},
    setCustomValidity(message){this.validation=message;},reportValidity(){},reset(){this.value='';},
    classList:{add(){},remove(){}},style:{}};
  Object.defineProperty(el,'firstChild',{get(){return this.children[0];}});
  Object.defineProperty(el,'textContent',{get(){return this._text||'';},set(text){this._text=text;this.children=[];}});
  return el;
}
function findById(list,id){
  for(const n of list){
    if(n.id===id)return n;
    const hit=findById(n.children||[],id);
    if(hit)return hit;
  }
  return null;
}
function portal(hash='',fetcher){
  const nodes=Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],element()]));
  const requests=[],window=new EventTarget();
  const location={origin:'https://example.test',pathname:'/owner-ui',search:'',hash};
  const context=vm.createContext({URL,URLSearchParams,Event,window,location,console,
    document:{getElementById:id=>nodes[id]||findById(Object.values(nodes),id),createElement:element,querySelectorAll:()=>[],
      addEventListener(){},removeEventListener(){}},
    history:{replaceState(_a,_b,url){location.hash='';location.replaced=url;}},
    navigator:{},confirm:()=>true,
    fetch:async(url,options)=>{
      requests.push({url,options,hashAtRequest:location.hash,replacedAtRequest:location.replaced});
      const data=fetcher?await fetcher(url,options):{};
      return {ok:true,status:200,json:async()=>data};
    }});
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
  return {nodes,context,location,requests,run:code=>vm.runInContext(code,context)};
}
test('invitation fragment is removed from the address bar before any HTTP request and never left in a form field',async()=>{
  const token='synthetic_invitation_'+'a'.repeat(32);
  const p=portal('#invite='+token);
  assert.equal(p.location.hash,'');
  assert.equal(p.location.replaced,'/owner-ui');
  const first=p.requests[0];
  assert.equal(first.url,'/owner/auth/invite');
  assert.equal(first.hashAtRequest,'','fragment must be gone before the first request leaves');
  assert.equal(first.replacedAtRequest,'/owner-ui');
  assert.equal(JSON.parse(first.options.body).token,token);
  assert.equal(p.nodes['redeem-token'].value,'');
});
test('a malformed invitation fragment is removed and never sent to the server',async()=>{
  const p=portal('#invite=short');
  assert.equal(p.location.hash,'');
  assert.equal(p.requests.some(r=>r.url==='/owner/auth/invite'),false);
});
test('an expired or used invitation link returns to sign-in with guidance',async()=>{
  const p=portal('#invite=synthetic_invitation_'+'c'.repeat(32),url=>{if(url==='/owner/auth/invite')throw new Error('Invitation expired');return [];});
  await new Promise(resolve=>setTimeout(resolve,10));
  assert.equal(p.nodes['login-form'].hidden,false);
  assert.match(p.nodes['login-help'].textContent,/expired or has already been used/);
});
test('sign-out clears private draft, invitation and identity fields before another customer enters',async()=>{
  const p=portal();
  const privateFields=['slug','email','composer-body','composer-url','social-hashtags','social-media','invite-email'];
  for(const field of privateFields)p.nodes[field].value='Synthetic A private data';
  p.nodes['invite-result'].textContent='Synthetic A invitation';
  p.nodes.identity.textContent='Synthetic A';
  p.run('bearer="synthetic-session-a"; currentRole="owner";');
  await p.nodes.logout.handlers.click();
  for(const field of privateFields)assert.equal(p.nodes[field].value,'',field);
  assert.equal(p.nodes['invite-result'].textContent,'');
  assert.equal(p.nodes.identity.textContent,'');
});
test('late HTTP results from customer A are rejected after the session changes to B',async()=>{
  let release;
  const p=portal('',()=>new Promise(resolve=>{release=resolve;}));
  p.run('bearer="synthetic-session-a";currentRole="owner";');
  const pending=p.run('request("/owner/social/accounts")');
  p.run('bearer="synthetic-session-b";');
  release([{display_name:'Synthetic A private account'}]);
  await assert.rejects(pending,error=>error.name==='SessionChangedError');
});
test('an invitation opens the correct workspace after password setup without re-entering the business ID',async()=>{
  const channels=Object.fromEntries(['telephone','call_recording','email_read','email_send','sms_read','sms_send','social']
    .map(key=>[key,{configured:false,active:false}]));
  const p=portal('#invite=synthetic_invitation_'+ 'a'.repeat(32),(url)=>{
    if(url==='/owner/auth/redeem')return {slug:'synthetic-a',email:'owner-a@example.test',role:'owner'};
    if(url==='/owner/auth/login')return {access_token:'synthetic-session-a'};
    if(url==='/owner/me')return {tenant:'synthetic-a',email:'owner-a@example.test',role:'owner'};
    if(url==='/owner/onboarding')return {business:{name:'Synthetic A',site_url:'https://example.test'},channels:{}};
    if(url==='/owner/onboarding/authorizations')return {};
    if(url==='/owner/onboarding/readiness')return {channels};
    if(url==='/owner/social/status')return {enabled:false,providers:{}};
    return [];
  });
  p.nodes['new-password'].value='SyntheticTestPassword123!';p.nodes['confirm-password'].value='SyntheticTestPassword123!';
  await p.nodes['redeem-form'].handlers.submit({preventDefault(){}});
  assert.equal(p.nodes['app-panel'].hidden,false);assert.equal(p.nodes['login-panel'].hidden,true);
  const login=p.requests.find(request=>request.url==='/owner/auth/login');assert.ok(login);
  assert.equal(JSON.parse(login.options.body).slug,'synthetic-a');
  assert.equal(p.nodes['new-password'].value,'');assert.equal(p.nodes['redeem-token'].value,'');
});
test('mismatching passwords do not consume the recovery token or contact the server',async()=>{
  const p=portal();
  const before=p.requests.length;
  p.nodes['redeem-token'].value='synthetic_recovery_'+'b'.repeat(32);
  p.nodes['new-password'].value='SyntheticPassword123!';p.nodes['confirm-password'].value='DifferentPassword123!';
  await p.nodes['redeem-form'].handlers.submit({preventDefault(){}});
  assert.equal(p.requests.length,before);assert.ok(p.nodes['redeem-token'].value);
});
test('a business file is reviewed locally before a customer chooses to save',async()=>{
  const p=portal();p.run('bearer="synthetic-session-a";currentRole="owner";');
  const before=p.requests.length;
  p.nodes['knowledge-file'].files=[{name:'Opening hours.md',size:45,text:async()=>'Synthetic business hours\n<script>data only</script>'}];
  await p.nodes['knowledge-file'].handlers.change();
  assert.equal(p.nodes['knowledge-title'].value,'Opening hours');
  assert.match(p.nodes['knowledge-text'].value,/<script>data only<\/script>/);
  assert.equal(p.requests.length,before);
});
test('an in-flight file read from A cannot populate B’s workspace after sign-out',async()=>{
  let release;
  const p=portal();p.run('bearer="synthetic-session-a";currentRole="owner";');
  p.nodes['knowledge-file'].files=[{name:'A-private.txt',size:30,text:()=>new Promise(resolve=>{release=resolve;})}];
  const loading=p.nodes['knowledge-file'].handlers.change();
  p.run('resetWorkspace();bearer="synthetic-session-b";currentRole="owner";');
  release('Synthetic A private business information');await loading;
  assert.equal(p.nodes['knowledge-text'].value,'');assert.equal(p.nodes['knowledge-title'].value,'');
});
