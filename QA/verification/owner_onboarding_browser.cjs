"use strict";
// Disposable browser verification of owner onboarding. No real API, CRM or customer data.
const {createRequire}=require("node:module");
const req=createRequire("/Users/jo/concierge/vm/nav-test/");
const puppeteer=req("puppeteer-core");
const http=require("node:http");
const fs=require("node:fs");
const path=require("node:path");
const html=fs.readFileSync(path.join(__dirname,"../../api/static/owner.html"),"utf8");
let role="owner",saved=null;
const permissions={};
const profile={
 business:{name:"Synthetic Business",site_url:"https://synthetic.example",
 greeting:"Welcome",notify_email:"owner@example.com",timezone:"Pacific/Auckland"},
 channels:{
  website_chat:{configured:true,verified:false},
  telephone:{configured:false,registered_numbers:0,verified:false},
  email:{configured:false,verified:false},
  social:{configured:false,verified:false}
 },customer_activation_enabled:false
};
function json(res,status,body){
 res.writeHead(status,{"content-type":"application/json","cache-control":"no-store"});
 res.end(JSON.stringify(body));
}
const server=http.createServer((request,res)=>{
 const url=new URL(request.url,"http://localhost");
 if(url.pathname==="/owner-ui"){
  res.writeHead(200,{"content-type":"text/html"});res.end(html);return;
 }
 const chunks=[];
 request.on("data",c=>chunks.push(c));
 request.on("end",()=>{
  const body=chunks.length?JSON.parse(Buffer.concat(chunks).toString("utf8")):{};
  if(url.pathname==="/owner/auth/login") return json(res,200,{access_token:"synthetic-only",expires_in:43200});
  if(url.pathname==="/owner/me") return json(res,200,{email:"owner@example.com",role,tenant:"synthetic"});
  if(url.pathname==="/owner/onboarding"&&request.method==="GET") return json(res,200,profile);
  if(url.pathname==="/owner/onboarding/profile"&&request.method==="PATCH"){
   if(role!=="owner")return json(res,403,{detail:"Owner role required"});
   saved=body;
   Object.assign(profile.business,body);
   return json(res,200,body);
  }
  if(url.pathname==="/owner/onboarding/authorizations"){
    if(request.method==="GET")return json(res,200,permissions);
    if(role!=="owner")return json(res,403,{detail:"Owner required"});
    if(body.authorized && !body.acknowledgement)return json(res,400,{detail:"Acknowledgement required"});
    permissions[body.channel]={authorized:body.authorized,provider_verified:false,active:false};
    return json(res,200,{channel:body.channel,...permissions[body.channel]});
  }
  if(url.pathname==="/owner/onboarding/readiness"){
    const keys=["telephone","call_recording","email_read","email_send","sms_read","sms_send","social"];
    return json(res,200,{business:"Synthetic Business",customer_activation_enabled:false,
      channels:Object.fromEntries(keys.map(k=>[k,{
        authorized:!!permissions[k]?.authorized,configured:false,provider_verified:false,active:false
      }]))});
  }
  if(url.pathname==="/owner/email-drafts") return json(res,200,[]);
  if(url.pathname==="/owner/phone-numbers") return json(res,200,[]);
  if(url.pathname==="/owner/phone-calls") return json(res,200,[]);
  if(url.pathname==="/owner/social/status") return json(res,200,{enabled:false,customer:"synthetic",live_publishing:false});
  if(url.pathname==="/owner/auth/logout")return json(res,200,{ok:true});
  return json(res,404,{detail:"Unknown local mock endpoint"});
 });
});
const check=(label,pass)=>{if(!pass)throw Error("FAIL "+label);console.log("PASS "+label);};
async function run(){
 await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
 const port=server.address().port;
 const browser=await puppeteer.launch({executablePath:"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",headless:"new",args:["--no-sandbox"]});
 try{
  for(const currentRole of ["owner","viewer"]){
   role=currentRole;
   profile.business.greeting="Welcome";
   const page=await browser.newPage();
   const errors=[];page.on("pageerror",e=>errors.push(String(e)));
   await page.goto("http://127.0.0.1:"+port+"/owner-ui");
   await page.type("#slug","synthetic");
   await page.type("#email","owner@example.com");
   await page.type("#password","TestOnlyPassword123!");
   await page.click("#login-form button[type=submit]");
   await page.waitForFunction(()=>document.querySelector("#onboarding-greeting").value==="Welcome");
   const text=await page.$eval("#onboarding-channels",e=>e.textContent);
   check(currentRole+" sees own business",text.includes("Synthetic Business"));
   check(currentRole+" sees unverified label",text.includes("provider test required"));
   await page.waitForFunction(()=>document.querySelectorAll("#channel-authorizations input[type=checkbox]").length===7);
   const authCount=await page.$$eval("#channel-authorizations input[type=checkbox]",els=>els.length);
   check(currentRole+" sees seven consent controls",authCount===7);
   const authDisabled=await page.$eval("#channel-authorizations input[type=checkbox]",e=>e.disabled);
   check(currentRole+" consent role protection",authDisabled===(currentRole!=="owner"));
   if(currentRole==="owner"){
     page.on("dialog",async dialog=>dialog.accept());
     await page.$eval("#channel-authorizations input[type=checkbox]",e=>e.click());
     await page.waitForFunction(()=>document.querySelector("#channel-authorizations input[type=checkbox]").checked);
     check("owner explicitly authorized one channel",permissions.telephone?.authorized===true);
     await page.$eval("#channel-authorizations input[type=checkbox]",e=>e.click());
     await page.waitForFunction(()=>!document.querySelector("#channel-authorizations input[type=checkbox]").checked);
     check("owner revoked same channel without activation",permissions.telephone?.authorized===false);
   }
   const disabled=await page.$eval("#onboarding-greeting",e=>e.disabled);
   check(currentRole+" profile edit rights",disabled===(currentRole!=="owner"));
   if(currentRole==="owner"){
    await page.$eval("#onboarding-greeting",e=>e.value="Hello from test");
    await page.click('#onboarding-form button[type="submit"]');
    await page.waitForFunction(()=>document.querySelector("#notice").textContent.includes("Business setup saved"));
    check("owner saved through existing portal",saved?.greeting==="Hello from test");
   }
   await page.click("#logout");
   await page.waitForSelector("#login-panel:not([hidden])");
   check(currentRole+" logout clears business fields",await page.$eval("#onboarding-greeting",e=>e.value===""));
   check(currentRole+" no JavaScript exceptions",errors.length===0);
   await page.close();
  }
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
}
run().catch(error=>{console.error(error);server.close();process.exitCode=1;});
