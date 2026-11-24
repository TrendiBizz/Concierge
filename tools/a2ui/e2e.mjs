import {chromium} from 'playwright';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
import os from 'node:os';
const base='http://127.0.0.1:18765';
const out=os.homedir()+'/Reports/a2ui';
await mkdir(out+'/shots',{recursive:true});
const browser=await chromium.launch({headless:true,channel:"chrome"});
const pages=JSON.parse(await readFile('pages.json','utf8'));
const results=[];
try {
 for(const viewport of [{width:1280,height:900},{width:390,height:844}]) {
  const mobile=viewport.width<500;
  const context=await browser.newContext({viewport});
  // No requests may reach external services, even analytics or fonts.
  await context.route('**/*',route=>route.request().url().startsWith(base)?route.continue():route.abort());
  for (const file of ['widget-preview',...pages.map(p=>p.file)]) {
   const page=await context.newPage();
   const errors=[];
   const shotPrefix=file==='widget-preview'?'concierge':file==='index.html'?'site':'page-'+file.replace(/\.html$/,'').replaceAll('/','--');
   page.on('pageerror',e=>{errors.push(e.message);console.log('BROWSER ERROR',e.message)});
   page.setDefaultTimeout(10000);
   page.on('response',async r=>{if(r.url().endsWith('/chat/action')&&r.status()!==200)console.log('ACTION ERROR',r.request().postData(),await r.text())});
   await page.addInitScript(()=>{window.cspProblems=[];document.addEventListener('securitypolicyviolation',e=>window.cspProblems.push({directive:e.violatedDirective,blocked:e.blockedURI}));});
   await page.goto(base+'/'+file);
   await page.getByRole('button',{name:'Open AI guide',exact:true}).click();
   await page.evaluate(()=>window.cspProblems=[]);
   const log=page.locator('#cc-root .log');
   const send=async message=>{
    await page.getByRole('textbox',{name:'Message',exact:true}).fill(message);
    await page.getByRole('button',{name:'Send',exact:true}).click();
   };
   const fields={quote:{email:'request@example.test',details:'Example quote request'},booking:{email:'request@example.test',when:'2027-06-15T14:30',timezone:'Pacific/Auckland'},contact:{email:'request@example.test',details:'Example contact request'},pricing:{}};
   const initial=(await (await page.request.get(base+'/__evidence')).json()).saved.length;
   for(const kind of ['quote','booking','contact','pricing']) {
    await send(kind);
    const card=page.locator(`a2ui-surface[data-surface-id^="cc-${kind}-"]`).last();
    await card.locator('button').waitFor().catch(async e=>{console.log(await page.locator('#cc-root').evaluate(n=>n.shadowRoot.innerHTML));throw e});
    for(const [key,value] of Object.entries(fields[kind])) await card.locator(`[id="${key}"] input`).fill(value);
    if(kind==='quote') {
      // Native constraints reject blank/invalid contact data without reaching the handler.
      await card.locator('[id="email"] input').fill('invalid');
      await card.locator('button').click();
      assert.equal((await (await page.request.get(base+'/__evidence')).json()).saved.length, initial);
      await card.locator('[id="email"] input').fill(fields[kind].email);
    }
    {
      await card.scrollIntoViewIfNeeded();
      await page.screenshot({path:`${out}/shots/${shotPrefix}-${kind}-${mobile?'mobile':'desktop'}.png`});
    }
    const before=(await (await page.request.get(base+'/__evidence')).json()).saved.length;
    const [response] = await Promise.all([page.waitForResponse(r=>r.url().endsWith('/chat/action')),card.locator('button').click()]);
    assert.equal(response.status(),200);
    const ack=await response.json();
    const confirmation=page.locator(`a2ui-surface[data-surface-id="${ack.a2ui.at(-1).beginRendering.surfaceId}"]`);
    await confirmation.locator('button').waitFor();
    if(kind==='quote') {
      await confirmation.scrollIntoViewIfNeeded();
      await page.screenshot({path:`${out}/shots/${shotPrefix}-confirmation-${mobile?'mobile':'desktop'}.png`});
    }
    const [ackResponse] = await Promise.all([page.waitForResponse(r=>r.url().endsWith('/chat/action')),confirmation.locator('button').click()]);
    assert.equal(ackResponse.status(),200);
    await page.waitForFunction(()=>document.querySelector('#cc-root').shadowRoot.querySelector('.status').textContent==='Request saved.');
    const evidence=await (await page.request.get(base+'/__evidence')).json();
    assert.equal(evidence.saved.length,before+1,`${file} ${kind} must preserve request through acknowledgement`);
    const recorded=evidence.saved.at(-1).text;
    for(const value of Object.values(fields[kind])) assert.ok(recorded.includes(value),`${file} ${kind}: submitted data missing`);
    assert.ok(await card.locator('button').isDisabled());
   }
   const csp=await page.evaluate(()=>window.cspProblems);
   // Existing page inline style attributes may be blocked under the site's own strict policy.
   // Every script violation and any style violation from chat/renderer is a failure.
   const scriptViolations=csp.filter(v=>v.directive.startsWith('script')||v.directive.startsWith('style'));
   assert.deepEqual(scriptViolations,[],file+' CSP script violations');
   assert.deepEqual(errors,[],file+' browser errors');
   results.push({page:file,viewport:mobile?'mobile':'desktop',cards:['quote','booking','contact','pricing','confirmation'],submissions:8,pass:true,cspViolations:csp,screenshots:['quote','booking','contact','pricing','confirmation'].map(kind=>`shots/${shotPrefix}-${kind}-${mobile?'mobile':'desktop'}.png`)});
   console.log('PASS',mobile?'mobile':'desktop',file);
   await page.close();
  }
  await context.close();
 }
 // Actual non-stream endpoint remains compatible with clients that don't advertise A2UI.
 const plain=await fetch(base+'/api/v1/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'test',session_id:'plain-test',message:'quote'})});
 const body=await plain.json(); assert.equal(body.a2ui.length,0);assert.ok(body.reply);
 await writeFile(out+'/page-results.json',JSON.stringify(results,null,2));
 console.log('PASS',results.length,'page/viewport cases; text fallback');
} finally {await browser.close();}
