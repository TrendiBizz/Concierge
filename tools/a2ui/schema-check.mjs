import Ajv from 'ajv';
import formats from 'ajv-formats';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
const ajv=new Ajv({strict:false}); formats(ajv);
const server=ajv.compile(JSON.parse(readFileSync(new URL('./schemas/server_to_client_with_standard_catalog.json',import.meta.url))));
const client=ajv.compile(JSON.parse(readFileSync(new URL('./schemas/client_to_server.json',import.meta.url))));
const fixtures=JSON.parse(execFileSync(process.env.PYTHON || 'python3',['-c',`import sys,json;sys.path.insert(0,'api');from app import a2ui;print(json.dumps({k:a2ui.card(k) for k in a2ui.FIELDS}))`],{cwd:new URL('../../',import.meta.url),encoding:'utf8'}));
for(const [kind,messages] of Object.entries(fixtures)) {
 for(const message of messages) if(!server(message)) throw Error(kind+JSON.stringify(server.errors));
 const userAction={name:'submit_'+kind,surfaceId:messages.at(-1).beginRendering.surfaceId,sourceComponentId:'submit',timestamp:new Date().toISOString(),context:{}};
 if(!client({userAction})) throw Error(JSON.stringify(client.errors));
}
console.log('PASS official upstream v0.8 schemas: 15 server messages and 5 userAction envelopes');
