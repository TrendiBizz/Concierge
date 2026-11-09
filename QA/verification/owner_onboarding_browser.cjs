"use strict";
// Disposable browser verification of owner onboarding. No real API, CRM or customer data.
const {createRequire}=require("node:module");
const req=createRequire("/Users/jo/concierge/vm/nav-test/");
const puppeteer=req("puppeteer-core");
const http=require("node:http");
const fs=require("node:fs");
const path=require("node:path");
const html=fs.readFileSync(path.join(__dirname,"../../api/static/owner.html"),"utf8");
let role="owner",saved=null,quote=null;
const lead={id:"00000000-0000-4000-8000-000000000001",name:"Fixture Contact",email:"contact@example.invalid",phone:"",message:"Please quote",channel:"chat",status:"new",created_at:new Date().toISOString()};
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
  if(url.pathname==="/owner/crm")return json(res,200,{leads:[lead],appointments:[],tasks:[]});
  if(url.pathname==="/owner/email-secretary/jobs")return json(res,200,[]);
  if(url.pathname==="/owner/calendar")return json(res,200,{configured:true,connected:false});
  if(url.pathname==="/owner/crm/quotations"){
   if(request.method==="GET")return json(res,200,quote?[quote]:[]);
   quote={...body,id:"fixture-quote",status:"draft",contact:lead,subtotal_cents:15002,tax_cents:2250,total_cents:17252,lines:body.lines.map(line=>({...line,amount_cents:15002}))};return json(res,201,quote);
  }
  if(url.pathname==="/owner/crm/quotations/fixture-quote/status"){quote.status=body.status;quote.version++;return json(res,200,quote);}
  if(url.pathname==="/owner/phone-setup")return json(res,200,{status:"not_requested"});
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
     await Promise.all([page.waitForResponse(response=>response.url().endsWith("/owner/onboarding/authorizations")&&response.request().method()!=="GET"),page.$eval("#channel-authorizations input[type=checkbox]",e=>e.click())]);
     await page.waitForFunction(()=>document.querySelector("#channel-authorizations input[type=checkbox]").checked);
     check("owner explicitly authorized one channel",permissions.telephone?.authorized===true);
     await Promise.all([page.waitForResponse(response=>response.url().endsWith("/owner/onboarding/authorizations")&&response.request().method()!=="GET"),page.$eval("#channel-authorizations input[type=checkbox]",e=>e.click())]);
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
   await page.waitForFunction(()=>document.querySelector("#calendar-status").textContent.includes("Ready to connect"));
   check(currentRole+" calendar connection role protection",await page.$eval("#calendar-connect",e=>e.hidden)===(currentRole!=="owner"));
   check(currentRole+" website voice and booking role protection",await page.$eval("#onboarding-voice",e=>e.disabled)===(currentRole!=="owner"));
   await page.waitForFunction(()=>document.querySelector("#quote-lead").options.length===1);
   check(currentRole+" quotation form role protection",await page.$eval("#quote-form",e=>e.hidden)===(currentRole==="viewer"));
   if(currentRole==="owner"){
    await page.type("#quote-title","Fixture proposal");await page.type('#quote-lines [data-key="description"]',"Service");
    await page.$eval('#quote-lines [data-key="quantity"]',e=>e.value="1.5");await page.type('#quote-lines [data-key="price"]',"100.01");
    await page.$eval("#quote-tax",e=>e.value="15");await page.click('#quote-form button[type="submit"]');
    await page.waitForFunction(()=>document.querySelector("#quote-list").textContent.includes("172.52"));
    check("quotation form submits integer cents and explicit tax",quote.lines[0].unit_price_cents===10001&&quote.tax_basis_points===1500);
    const review=await page.$$("#quote-list button");for(const button of review)if(await button.evaluate(e=>e.textContent)==="Mark reviewed")await button.click();
    await page.waitForFunction(()=>document.querySelector("#quote-list").textContent.includes("· reviewed"));
    check("reviewed quotation removes price edit control",!(await page.$eval("#quote-list",e=>e.textContent)).includes("Edit draft"));
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
