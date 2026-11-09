'use strict';
// Real deployed portal/API/DB. Only disposable fixture users, no mocks or sends.
const fs=require('node:fs');
const {createRequire}=require('node:module');
const req=createRequire('/Users/jo/concierge/vm/nav-test/');
const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const check=(label,ok)=>{if(!ok)throw Error('FAIL '+label);console.log('PASS '+label);};
async function run(){
 const browser=await req('puppeteer-core').launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:'new',args:['--no-sandbox']});
 try{
  for(const role of ['owner','viewer']){
   const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
   const response=await page.goto('https://concierge.trendibizz.com/owner-ui',{waitUntil:'domcontentloaded'});
   check(role+' public deployed portal responds',response.status()===200);
   await page.type('#slug',config.slug);await page.type('#email',role+'@example.invalid');await page.type('#password',config.password);await page.click('#login-form button[type=submit]');
   await page.waitForFunction(()=>document.querySelector('#onboarding-name').value==='Portal browser fixture');
   await page.waitForFunction(()=>document.querySelector('#quote-lead').options.length===1);
   check(role+' real tenant CRM and profile load',await page.$eval('#crm-leads',e=>e.textContent.includes('Fixture Contact')));
   check(role+' booking and voice editing permissions',await page.$eval('#onboarding-voice',e=>e.disabled)===(role!=='owner'));
   check(role+' quotation editing permissions',await page.$eval('#quote-form',e=>e.hidden)===(role==='viewer'));
   await page.waitForFunction(()=>document.querySelector('#calendar-status').textContent.includes('Ready to connect'));
   check(role+' deployed private Google app configured',await page.$eval('#calendar-connect',e=>e.hidden)===(role!=='owner'));
   if(role==='owner'){
    const start=await page.evaluate(async()=>{const result=await request('/owner/calendar/start','POST');const url=new URL(result.authorization_url);return {secure:url.origin==='https://accounts.google.com',state:result.state.length>=32,scopes:url.searchParams.get('scope'),callback:url.searchParams.get('redirect_uri')};});
    check('real owner OAuth start is tenant/session bound with exact callback',start.secure&&start.state&&start.scopes.includes('calendar.freebusy')&&start.scopes.includes('calendar.events')&&start.callback==='https://concierge.trendibizz.com/owner/social/oauth/callback');
    await page.$eval('#onboarding-voice',e=>e.checked=true);await page.$eval('#onboarding-booking',e=>e.checked=true);await page.click('#onboarding-form button[type=submit]');
    await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('Business setup saved'));
    check('owner saves actual website voice and booking settings',await page.$eval('#onboarding-voice',e=>e.checked)&&await page.$eval('#onboarding-booking',e=>e.checked));
    await page.type('#quote-title','Deployed synthetic proposal');await page.type('#quote-lines [data-key=description]','Synthetic service');await page.$eval('#quote-lines [data-key=quantity]',e=>e.value='1.5');await page.type('#quote-lines [data-key=price]','100.01');await page.$eval('#quote-tax',e=>e.value='15');await page.click('#quote-form button[type=submit]');
    await page.waitForFunction(()=>document.querySelector('#quote-list').textContent.includes('172.52'));
    check('real quotation pricing saves 150.02 subtotal plus 22.50 tax',await page.$eval('#quote-list',e=>e.textContent.includes('150.02')&&e.textContent.includes('22.50')));
    for(const button of await page.$$('#quote-list button'))if(await button.evaluate(e=>e.textContent)==='Mark reviewed')await button.click();
    await page.waitForFunction(()=>document.querySelector('#quote-list').textContent.includes('· reviewed'));
    check('real reviewed quotation locks price editing',await page.$eval('#quote-list',e=>!e.textContent.includes('Edit draft')));
   }else{
    const forbidden=await page.evaluate(async()=>{try{await request('/owner/calendar/start','POST');return false;}catch(error){return error.message.includes('permissions');}});
    check('viewer cannot start real Google authorization',forbidden);
   }
   await page.click('#logout');await page.waitForSelector('#login-panel:not([hidden])');
   check(role+' logout clears real quotation and business state',await page.$eval('#quote-list',e=>!e.textContent)&&await page.$eval('#onboarding-name',e=>!e.value));
   check(role+' no browser JavaScript exceptions',errors.length===0);
   await page.close();
  }
 }finally{await browser.close();}
}
run().catch(error=>{console.error(error.message);process.exitCode=1;});
