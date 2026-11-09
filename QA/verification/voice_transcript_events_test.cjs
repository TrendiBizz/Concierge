const fs=require('node:fs');const vm=require('node:vm');const assert=require('node:assert/strict');
const source=fs.readFileSync('api/static/widget.js','utf8');
const start=source.indexOf('    function onServerEvent(raw) {');
const end=source.indexOf('    function stopVoice()',start);
const logs=[];
const context={JSON,Promise,console,userText:'',assistantText:'',pendingCalls:[],completedInputIds:new Set(),
 logVoice:(role,text)=>logs.push({role,text}),setStatus:()=>{},playChunk:()=>{},interrupt:()=>{},wsSend:()=>{},runToolCall:()=>Promise.resolve({})};
vm.createContext(context);vm.runInContext(source.slice(start,end),context);
context.onServerEvent(JSON.stringify({type:'conversation.item.input_audio_transcription.completed',item_id:'turn1',transcript:'Please text me the details'}));
assert.equal(logs.length,1,'Final Grok caller transcript must be persisted even without a subsequent audio response');
assert.equal(logs[0].text,'Please text me the details');
context.onServerEvent(JSON.stringify({type:'conversation.item.input_audio_transcription.completed',item_id:'turn1',transcript:'Please text me the details'}));
assert.equal(logs.length,1,'Replayed final transcript must not create a duplicate');
console.log('PASS final caller transcript saved once before another response');
