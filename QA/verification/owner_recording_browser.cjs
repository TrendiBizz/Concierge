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
let delivery=null;
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
  if(url.pathname==="/owner/mobile-connection")return json(res,200,{status:"ready_to_forward",destination:"+6495550100",carrier:"spark_nz",last_call:null,steps:[{label:"Forward unanswered calls",dial:"*61*+6495550100*11#",check:"*#61*11#"}]});
  if(url.pathname==="/owner/phone-setup")return json(res,200,{status:"not_requested"});
  if(url.pathname==="/owner/sms-phone")return json(res,200,{paired:false,online:false,messages:[]});
  if(url.pathname==="/owner/knowledge")return json(res,200,[]);
  if(url.pathname==="/owner/crm")return json(res,200,{leads:[{id:"11111111-1111-4111-8111-111111111111",name:"Fixture caller",phone:"+64215550100",email:"caller@example.invalid",message:"Please send details",channel:"voice",status:"new",created_at:new Date().toISOString(),consent_contact:true}],appointments:[],tasks:[]});
  if(url.pathname.endsWith("/transcript"))return json(res,200,[{role:"user",content:"Please send details"},{role:"assistant",content:"The team will follow up"}]);
  if(url.pathname.endsWith("/recordings"))return json(res,200,[{session_id:"22222222-2222-4222-8222-222222222222",mime_type:"audio/webm",created_at:new Date().toISOString()}]);
  if(url.pathname==="/owner/voice-recordings/22222222-2222-4222-8222-222222222222"){
   if(request.headers.authorization!=="Bearer synthetic-only")return json(res,401,{});
   res.writeHead(200,{"content-type":"audio/webm"});return res.end(fs.readFileSync("/tmp/trendi-recording-fixture.webm"));
  }
  if(url.pathname.endsWith("/share"))return json(res,200,{url:"https://example.invalid/private-fixture-share",expires_in_hours:24});
  if(url.pathname.endsWith("/deliver")){delivery=body;return json(res,200,{status:"queued",note:"Delivery is queued; it has not been confirmed sent."});}
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
   const page=await browser.newPage();await page.setViewport({width:1280,height:900});
   const errors=[];page.on("pageerror",e=>errors.push(String(e)));
   await page.goto("http://127.0.0.1:"+port+"/owner-ui");
   await page.type("#slug","synthetic");
   await page.type("#email","owner@example.com");
   await page.type("#password","TestOnlyPassword123!");
   await page.click("#login-form button[type=submit]");
   await page.waitForFunction(()=>document.querySelector("#onboarding-greeting").value==="Welcome");
   check(currentRole+" smartphone setup selected",await page.$eval("#phone-connection",select=>select.value==="mobile_forwarding"));
   check(currentRole+" sees destination without false live status",await page.$eval("#mobile-connection",host=>host.textContent.includes("+6495550100")&&!host.textContent.includes("Connected")));
   check(currentRole+" forwarding code access",await page.$eval("#mobile-connection",(host,role)=>host.textContent.includes("*61*")===(role==="owner"),currentRole));
   await page.click("#crm-leads summary");
   await page.waitForFunction(()=>document.querySelector("#crm-leads").textContent.includes("Load recording"));
   await page.evaluate(()=>Array.from(document.querySelectorAll("#crm-leads button")).find(b=>b.textContent==="Load recording").click());
   await page.waitForSelector("#crm-leads audio");
   check(currentRole+" loads private recording",await page.$eval("#crm-leads audio",audio=>audio.src.startsWith("blob:")));
   if(currentRole==="owner"){
    page.on("dialog",async dialog=>dialog.accept());
    await page.evaluate(()=>Array.from(document.querySelectorAll("#crm-leads button")).find(b=>b.textContent.includes("24-hour")).click());
    await page.waitForSelector('#crm-leads input[aria-label="Private recording sharing link"]');
    await page.evaluate(()=>document.querySelector('#crm-leads select[aria-label="Conversation copy format"]').value="22222222-2222-4222-8222-222222222222");
    await page.evaluate(()=>Array.from(document.querySelectorAll("#crm-leads button")).find(b=>b.textContent==="Send conversation copy").click());
    await page.waitForFunction(()=>document.querySelector("#notice").textContent.includes("Delivery is queued"));
    check("explicit delivery preserves recipient and recording",delivery?.recipient==="+64215550100"&&delivery?.content==="recording");
   }else check("viewer cannot share or send",!await page.$('#crm-leads select[aria-label="Send copy to customer"]'));
   if(currentRole==="owner")await page.screenshot({path:"/tmp/trendi-owner-recording-preview.png",fullPage:true});
   await page.click("#logout");
   await page.waitForSelector("#login-panel:not([hidden])");
   check(currentRole+" logout clears mobile destination",await page.$eval("#mobile-connection",host=>host.textContent===""));
   check(currentRole+" logout removes audio",!await page.$("audio"));
   check(currentRole+" no JavaScript exceptions",errors.length===0);
   await page.close();
  }
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
}
run().catch(error=>{console.error(error);server.close();process.exitCode=1;});
