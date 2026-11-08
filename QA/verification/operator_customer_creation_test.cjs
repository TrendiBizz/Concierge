// Offline contract for the real operator form, with synthetic HTTP responses.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('api/static/admin.html','utf8');
function element(){return {value:'',hidden:false,children:[],handlers:{},style:{},
  addEventListener(k,fn){this.handlers[k]=fn;},setAttribute(){},appendChild(v){this.children.push(v);return v;},
  reset(){},focus(){},click(){return this.handlers.click?.();},textContent:''};}
test('retrying a failed owner invitation reuses the created workspace',async()=>{
  const nodes=Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],element()]));
  let creates=0,invites=0;const requests=[];
  vm.runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],{
    document:{getElementById:id=>nodes[id],createElement:element,createTextNode:t=>t},URL,Node:class{},
    sessionStorage:{getItem(){return null;},setItem(){},removeItem(){}},alert(){},
    fetch:async(url,opts)=>{
      requests.push({url,opts});let body={},status=200;
      if(url==='/admin/tenants' && opts.method==='POST'){
        creates++;body={slug:'synthetic-a',name:'Synthetic A'};
      }else if(url.includes('/owner-invitations')){
        invites++;if(invites===1){status=400;body={detail:'Synthetic invitation failure'};}
        else body={invitation_url:'https://example.test/owner-ui#invite=synthetic-only'};
      }else if(url==='/admin/tenants')body=[];
      return {ok:status===200,status,json:async()=>body,text:async()=>JSON.stringify(body)};
    }
  });
  nodes['new-customer-name'].value='Synthetic A';nodes['new-customer-email'].value='owner@example.test';
  await nodes['new-customer-form'].handlers.submit({preventDefault(){}});
  assert.equal(creates,1);assert.equal(invites,1);
  assert.match(nodes['create-customer'].textContent,/Retry invitation/);
  await nodes['new-customer-form'].handlers.submit({preventDefault(){}});
  assert.equal(creates,1);assert.equal(invites,2);
  assert.ok(nodes['new-customer-result'].children.some(child=>child.value==='https://example.test/owner-ui#invite=synthetic-only'));
  assert.ok(requests.filter(request=>request.url.includes('/owner-invitations')).every(request=>request.url.includes('/synthetic-a/')));
});
