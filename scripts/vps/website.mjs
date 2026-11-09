// Serve the original Cloudflare worker and website assets on a standard Node host.
// No production content or worker implementation is forked here.
import http from 'node:http';
import fs from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import {Readable} from 'node:stream';
import path from 'node:path';
const {default:worker}=await import('data:text/javascript;base64,'+
  (await fs.readFile('/website/deploy_known_good/_worker.js')).toString('base64'));

const root = '/website/site';
const mime = {'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8',
  '.js':'application/javascript','.json':'application/json','.txt':'text/plain; charset=utf-8',
  '.xml':'application/xml','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg',
  '.jpeg':'image/jpeg','.ico':'image/x-icon','.woff2':'font/woff2','.woff':'font/woff',
  '.mp4':'video/mp4','.webp':'image/webp','.pdf':'application/pdf','.csv':'text/csv'};
const blocks = [];
for (const line of (await fs.readFile(path.join(root,'_headers'),'utf8')).split('\n')) {
  if (!line.trim() || line.trim().startsWith('#')) continue;
  if (!/^\s/.test(line)) blocks.push({pattern:line.trim(), headers:{}});
  else if (blocks.length && line.includes(':')) {
    const colon=line.indexOf(':');blocks.at(-1).headers[line.slice(0,colon).trim()]=line.slice(colon+1).trim();
  }
}
const redirects=(await fs.readFile(path.join(root,'_redirects'),'utf8')).split('\n')
  .map(line=>line.trim()).filter(line=>line && !line.startsWith('#')).map(line=>line.split(/\s+/));
function matches(pattern,value) {
  return new RegExp('^'+pattern.split('*').map(part=>part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('.*')+'$').test(value);
}
async function asset(request) {
  let pathname;
  try { pathname=decodeURIComponent(new URL(request.url).pathname); }
  catch { return new Response('Bad request',{status:400}); }
  if (pathname.includes('\0') || pathname.split('/').some(part=>part.startsWith('.') && part!=='.well-known') || ['/_headers','/_redirects','/_worker.js','/_routes.json'].includes(pathname))
    return new Response('Not found',{status:404});
  for (const [from,to,status='302'] of redirects) {
    if (pathname===from) {
      const code=Number(status);
      if (code>=300 && code<400) return new Response(null,{status:code,headers:{Location:to}});
      if (code===404) return new Response('Not found',{status:404});
    }
  }
  const relative=pathname==='/'?'index.html':pathname.replace(/^\//,'');
  let file,stat;
  for (const candidate of [relative,relative+'.html',path.join(relative,'index.html')]) {
    const resolved=path.resolve(root,candidate);
    if (!resolved.startsWith(root+'/')) continue;
    try {
      const real=await fs.realpath(resolved);
      if (!real.startsWith(root+'/')) continue;
      const info=await fs.stat(real);
      if(info.isFile()){file=real;stat=info;break;}
    }catch{}
  }
  let status=200;
  if(!file){file=path.join(root,'404.html');stat=await fs.stat(file);status=404;}
  const headers={'Content-Type':mime[path.extname(file)]||'application/octet-stream','Accept-Ranges':'bytes'};
  for(const block of blocks)if(matches(block.pattern,pathname))Object.assign(headers,block.headers);
  let start=0,end=stat.size-1;
  if(status===200 && request.headers.has('range')) {
    const match=/^bytes=(\d*)-(\d*)$/.exec(request.headers.get('range'));
    if(!match || (!match[1]&&!match[2]))return new Response(null,{status:416});
    if(!match[1])start=Math.max(0,stat.size-Number(match[2]));
    else {start=Number(match[1]);if(match[2])end=Math.min(end,Number(match[2]));}
    if(start>end || start>=stat.size)return new Response(null,{status:416,headers:{'Content-Range':`bytes */${stat.size}`}});
    status=206;headers['Content-Range']=`bytes ${start}-${end}/${stat.size}`;
  }
  headers['Content-Length']=String(end-start+1);
  return new Response(request.method==='HEAD'?null:Readable.toWeb(createReadStream(file,{start,end})),{status,headers});
}
http.createServer(async(incoming,outgoing)=>{
  try {
    let size=0;const body=[];
    for await(const chunk of incoming){size+=chunk.length;if(size>1048576){outgoing.writeHead(413).end();return;}body.push(chunk);}
    const method=incoming.method;
    const request=new Request('https://'+incoming.headers.host+incoming.url,{method,headers:incoming.headers,
      ...(method!=='GET'&&method!=='HEAD'?{body:Buffer.concat(body)}:{})});
    const response=await worker.fetch(request,{PAGESPEED_API_KEY:process.env.PAGESPEED_API_KEY,ASSETS:{fetch:asset}},{waitUntil:promise=>promise.catch(()=>{})});
    outgoing.writeHead(response.status,Object.fromEntries(response.headers));
    if(method==='HEAD'||!response.body)outgoing.end();
    else Readable.fromWeb(response.body).pipe(outgoing);
  }catch{
    outgoing.writeHead(502,{'Content-Type':'text/plain'}).end('Website temporarily unavailable');
  }
}).listen(8080,'0.0.0.0');
