'use strict';
const {createRequire}=require('node:module');
const req=createRequire('/Users/jo/concierge/vm/nav-test/');
const puppeteer=req('puppeteer-core');
const http=require('node:http'),fs=require('node:fs'),assert=require('node:assert/strict');
const widget=fs.readFileSync('api/static/widget.js');
const realGrok=fs.existsSync('/tmp/trendi-grok-recording-test.pcm')?fs.readFileSync('/tmp/trendi-grok-recording-test.pcm').toString('base64'):null;
let audio=null,finished=false,logs=[];
const requests=[];
const server=http.createServer((request,response)=>{requests.push(request.url);
 let chunks=[];request.on('data',chunk=>chunks.push(chunk));request.on('end',()=>{
  const body=Buffer.concat(chunks);const json=(data)=>{response.setHeader('Content-Type','application/json');response.end(JSON.stringify(data));};
  if(request.url==='/widget.js'){response.setHeader('Content-Type','application/javascript');return response.end(widget);}
  if(request.url.startsWith('/api/v1/widget-config'))return json({name:'Fixture business',accent_color:'#123456',cta_text:'Ask',voice_enabled:true,recording_available:true,greeting:'Fixture'});
  if(request.url==='/api/v1/voice/token'){
   assert.equal(JSON.parse(body).recording_consent,true);return json({token:'test-only',url:'wss://fixture.invalid',session:{voice:'ara'},voice_session:{id:'11111111-1111-4111-8111-111111111111',token:'test-only-session-token',recording:true}});
  }
  if(request.url==='/api/v1/voice/log'){logs.push(JSON.parse(body));return json({ok:true});}
  if(request.url.endsWith('/recording')){audio=body;return json({ok:true});}
  if(request.url.endsWith('/finish')){finished=true;return json({ok:true});}
  if(request.url==='/'){
   response.setHeader('Content-Type','text/html');return response.end(`<!doctype html><meta charset="utf-8"><title>Recording fixture</title><script>
    class FixtureSocket {
     constructor(){this.readyState=1;setTimeout(()=>this.onopen&&this.onopen(),40);}
     send(raw){const e=JSON.parse(raw);if(e.type==='response.create'&&!this.started){this.started=true;setTimeout(()=>{
      const emit=e=>this.onmessage({data:JSON.stringify(e)});
      emit({type:'conversation.item.input_audio_transcription.completed',item_id:'caller-turn',transcript:'Please send me the details'});
      const pcm=new Int16Array(24000);for(let i=0;i<pcm.length;i++)pcm[i]=Math.sin(i*2*Math.PI*880/24000)*8000;
      const bytes=new Uint8Array(pcm.buffer);let str='';for(const b of bytes)str+=String.fromCharCode(b);
      emit({type:'response.output_audio.delta',delta:${JSON.stringify(realGrok)}||btoa(str)});
      emit({type:'response.output_audio_transcript.delta',delta:'Your request is saved'});emit({type:'response.done'});
     },100);}}
     close(){this.readyState=3;this.onclose&&this.onclose();}
    }window.WebSocket=FixtureSocket;
   </script><script src='/widget.js' data-key='fixture-key' data-autoopen='1'></script>`);
  }
  response.statusCode=404;response.end();
 });
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await puppeteer.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:'new',args:['--no-sandbox','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--autoplay-policy=no-user-gesture-required']});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(String(error)));
  await page.goto('http://127.0.0.1:'+server.address().port);
  await page.waitForFunction(()=>document.querySelector('[data-concierge-host]')||Array.from(document.querySelectorAll('div')).some(node=>node.shadowRoot));
  await page.evaluate(()=>{const root=Array.from(document.querySelectorAll('div')).find(node=>node.shadowRoot).shadowRoot;root.querySelector('input[type=checkbox]').click();root.querySelector('.mic').click();});
  await new Promise(resolve=>setTimeout(resolve,3500));

  await page.waitForFunction(()=>Array.from(document.querySelectorAll('div')).find(node=>node.shadowRoot).shadowRoot.querySelector('.status').textContent.includes('Listening'),{timeout:12000});
  await new Promise(resolve=>setTimeout(resolve,2200));
  await page.evaluate(()=>{Array.from(document.querySelectorAll('div')).find(node=>node.shadowRoot).shadowRoot.querySelector('.mic').click();});
  for(let i=0;i<100&&!finished;i++)await new Promise(resolve=>setTimeout(resolve,50));
  if(!audio)console.error('Fixture diagnostics',JSON.stringify({logs,errors,widget:await page.evaluate(()=>Array.from(document.querySelectorAll('div')).find(node=>node.shadowRoot).shadowRoot.textContent.slice(-1800))}));
  assert(finished,'Voice session completion must be sent');assert(audio&&audio.length>3000,'Mixed audio must be uploaded');
  assert.equal(audio.subarray(0,4).toString('hex'),'1a45dfa3');
  assert(logs.some(row=>row.role==='user'&&row.text==='Please send me the details'));
  assert(logs.some(row=>row.role==='assistant'&&row.text==='Your request is saved'));
  assert.equal(errors.length,0,errors.join('\n'));
  fs.writeFileSync('/tmp/trendi-recording-fixture.webm',audio,{mode:0o600});
  console.log(JSON.stringify({pass:true,audio_bytes:audio.length,transcript_roles:logs.map(row=>row.role),recording:'/tmp/trendi-recording-fixture.webm',assistant_audio:realGrok?'genuine Grok Ara test sentence':'synthetic tone',note:'Synthetic caller microphone; not a carrier call'}));
 }finally{await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
