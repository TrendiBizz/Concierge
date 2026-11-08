"use strict";
// Browser regression: OAuth callback reaches its originating Concierge tab even
// when a provider's COOP headers sever window.opener. No real credentials used.
const {createRequire}=require("node:module");
const req=createRequire("/Users/jo/concierge/vm/nav-test/");
const puppeteer=req("puppeteer-core");
const http=require("node:http");
const fs=require("node:fs");
const path=require("node:path");
const assert=require("node:assert/strict");
const root=path.join(__dirname,"../../api/static");
const owner=fs.readFileSync(path.join(root,"owner.html"),"utf8");
const callback=fs.readFileSync(path.join(root,"social-oauth-callback.html"),"utf8");
const state="A".repeat(43), code="synthetic-code";
let finished=0, lastFinish=null;
const server=http.createServer((request,response)=>{
 const url=new URL(request.url,"http://localhost");
 const send=(status,obj)=>{
  response.writeHead(status,{"content-type":"application/json","cache-control":"no-store"});
  response.end(JSON.stringify(obj));
 };
 if(url.pathname==="/owner-ui"||url.pathname==="/owner/social/oauth/callback"){
  response.writeHead(200,{"content-type":"text/html","cache-control":"no-store"});
  return response.end(url.pathname==="/owner-ui"?owner:callback);
 }
 let chunks=[];
 request.on("data",part=>chunks.push(part));
 request.on("end",()=>{
  const data=chunks.length?JSON.parse(Buffer.concat(chunks).toString()):{};
  if(url.pathname==="/owner/auth/login")return send(200,{access_token:"synthetic-only"});
  if(url.pathname==="/owner/me")return send(200,{email:"owner@example.test",role:"owner",tenant:"synthetic"});
  if(url.pathname==="/owner/onboarding")return send(200,{business:{name:"Synthetic"},channels:{}});
  if(url.pathname==="/owner/onboarding/authorizations")return send(200,{});
  if(url.pathname==="/owner/onboarding/readiness")return send(200,{channels:Object.fromEntries(["telephone","call_recording","email_read","email_send","sms_read","sms_send","social"].map(k=>[k,{configured:false,active:false}]))});
  if(["/owner/phone-numbers","/owner/phone-calls","/owner/email-drafts","/owner/social/accounts","/owner/social/posts"].includes(url.pathname))return send(200,[]);
  if(url.pathname==="/owner/social/status")return send(200,{enabled:true,providers:{linkedin:true},live_publishing:false});
  if(url.pathname==="/owner/social/oauth/linkedin/start")return send(200,{
   authorization_url:"https://www.linkedin.com/oauth/v2/authorization?state="+state,
   state
  });
  if(url.pathname==="/owner/social/oauth/linkedin/finish"){
   finished++;lastFinish=data;return send(200,{account_id:"synthetic-account"});
  }
  return send(404,{detail:"Unknown synthetic endpoint"});
 });
});
async function main(){
 await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
 const base="http://127.0.0.1:"+server.address().port;
 const browser=await puppeteer.launch({executablePath:"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",headless:"new",args:["--no-sandbox"]});
 try{
  const ownerPage=await browser.newPage();
  await ownerPage.goto(base+"/owner-ui");
  await ownerPage.type("#slug","synthetic");
  await ownerPage.type("#email","owner@example.test");
  await ownerPage.type("#password","SyntheticPassword123!");
  await ownerPage.click("#login-form button[type=submit]");
  await ownerPage.waitForFunction(()=>{const b=document.querySelector("#social-linkedin-connect");return !b.hidden&&!b.disabled;},{timeout:8000});
  await ownerPage.click("#social-linkedin-connect");
  await ownerPage.waitForFunction(()=>document.querySelector("#notice").textContent.includes("linking is not available") || !!document.querySelector("#social-linkedin-connect"),{timeout:2000});
  await new Promise(resolve=>setTimeout(resolve,500));
  // This callback is an independent tab, with no opener, as can happen with COOP.
  const returned=await browser.newPage();
  await returned.goto(base+"/owner/social/oauth/callback?state="+state+"&code="+code);
  await new Promise(resolve=>setTimeout(resolve,1200));
  await ownerPage.waitForFunction(()=>document.querySelector("#notice").textContent.includes("account connected"),{timeout:4000});
  assert.equal(finished,1);
  assert.deepEqual(lastFinish,{state,code});
  assert.equal(await returned.evaluate(()=>window.opener),null);
  console.log("PASS lost-opener callback reconnects to signed-in owner tab");
  const result=await ownerPage.$eval("#notice",el=>el.textContent);
  assert.match(result,/posting remains disabled/i);
  console.log("PASS publishing remains disabled");
  await ownerPage.close();
 }finally{
  await browser.close();
  await new Promise(resolve=>server.close(resolve));
 }
}
main().catch(err=>{console.error(err);server.close();process.exitCode=1;});
