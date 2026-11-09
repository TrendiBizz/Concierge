const {createRequire}=require("module");
const req=createRequire("/Users/jo/concierge/vm/nav-test/");
const puppeteer=req("puppeteer-core");
const BASE="http://127.0.0.1:18083";
const H={"X-Admin-Token":"owner-portal-test","Content-Type":"application/json"};
let passes=0;
function check(label,condition){if(!condition)throw Error("FAIL "+label);console.log("PASS "+label);passes++;}
async function admin(path,body){const r=await fetch(BASE+path,{method:"POST",headers:H,body:JSON.stringify(body)});if(!r.ok)throw Error(path+" "+r.status+" "+await r.text());return r.json();}
(async()=>{
 const browser=await puppeteer.launch({executablePath:"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",headless:"new",args:["--no-sandbox"]});
 try{
  const errors=[];
  const page=await browser.newPage();
  page.on("pageerror",e=>errors.push(String(e)));
  await admin("/admin/tenants",{slug:"portal-a",name:"Portal A",site_url:"https://portal-a.example",allowed_origins:[]});
  const invitation=await admin("/admin/tenants/portal-a/owner-invitations",{email:"owner@portal-a.example",role:"owner"});
  const redemption=await fetch(BASE+"/owner/auth/redeem",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:invitation.invitation_token,password:"ThisIsALongLocalTestPass123!"})});
  check("owner invitation accepted",redemption.status===200);
  const response=await page.goto(BASE+"/owner-ui");
  check("owner portal served",response.status()===200);
  await page.type("#slug","portal-a");
  await page.type("#email","owner@portal-a.example");
  await page.type("#password","ThisIsALongLocalTestPass123!");
  await page.click("#login-form button[type=submit]");
  await page.waitForSelector("#app-panel:not([hidden])",{timeout:8000});
  const identity=await page.$eval("#identity",e=>e.textContent);
  check("correct tenant and role displayed",identity.includes("portal-a")&&identity.includes("(owner)"));
  check("owner invitation panel visible",await page.$eval("#invite-panel",e=>!e.hidden));
  check("no token in persistent browser storage",await page.evaluate(()=>localStorage.length===0&&sessionStorage.length===0));
  check("no JavaScript errors",errors.length===0);
  await page.click("#logout");
  await page.waitForSelector("#login-panel:not([hidden])",{timeout:8000});
  check("logout returns to signin",await page.$eval("#app-panel",e=>e.hidden));
  console.log(passes+"/"+passes+" owner portal Chrome checks passed");
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
