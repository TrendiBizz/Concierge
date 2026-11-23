// Serve the original Cloudflare worker and website assets on a standard Node host.
// No production content or worker implementation is forked here.
import http from 'node:http';
import fs from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import {Readable} from 'node:stream';
import path from 'node:path';
import {randomBytes} from 'node:crypto';
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
// _redirects is re-read when its mtime changes, so an rsync takes effect without a restart. Exact-path matching only.
const redirectsFile=path.join(root,'_redirects');
let redirects=[], redirectsStamp=-1;
async function loadRedirects() {
  let stamp;
  try { stamp=(await fs.stat(redirectsFile)).mtimeMs; } catch { return redirects; }
  if (stamp===redirectsStamp) return redirects;
  try {
    redirects=(await fs.readFile(redirectsFile,'utf8')).split('\n')
      .map(line=>line.trim()).filter(line=>line && !line.startsWith('#')).map(line=>line.split(/\s+/));
    redirectsStamp=stamp;
  } catch { /* keep the last good table */ }
  return redirects;
}
await loadRedirects();
function matches(pattern,value) {
  return new RegExp('^'+pattern.split('*').map(part=>part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('.*')+'$').test(value);
}
async function asset(request) {
  let pathname;
  try { pathname=decodeURIComponent(new URL(request.url).pathname); }
  catch { return new Response('Bad request',{status:400}); }
  if (pathname.includes('\0') || pathname.split('/').some(part=>part.startsWith('.') && part!=='.well-known') || ['/_headers','/_redirects','/_worker.js','/_routes.json'].includes(pathname))
    return new Response('Not found',{status:404});
  // A 410 rule in _redirects ("/old-page /404.html 410") marks a deliberately removed page: it is served with
  // the site's 404 page as the body and status 410 Gone, so search engines drop it instead of retrying a 404.
  let gone=false;
  for (const [from,to,status='302'] of await loadRedirects()) {
    if (pathname===from) {
      const code=Number(status);
      if (code>=300 && code<400) return new Response(null,{status:code,headers:{Location:to}});
      if (code===404) return new Response('Not found',{status:404});
      if (code===410) { gone=true; break; }
    }
  }
  // SEO-ENGINE-301 (15 Nov 2026, ranking plan item 13): one URL per page.
  // 301 /page.html and /page/ to /page when site/page.html exists. Only lowercase [a-z0-9/-] page paths,
  // so .txt/.xml/.json/.js/.css/images, the IndexNow key, /llms.txt, /robots.txt and /sitemap.xml never match.
  // /concierge/*, /cdn-cgi/*, /.well-known/*, asset folders and /404 are excluded. Query string is kept.
  if (!gone) {
    let clean=null;
    if (/^\/[a-z0-9][a-z0-9\/-]*\.html$/.test(pathname)) clean=pathname.slice(0,-5);
    else if (/^\/[a-z0-9][a-z0-9\/-]*[a-z0-9]\/$/.test(pathname)) clean=pathname.slice(0,-1);
    if (clean==='/index') clean='/';
    const keep=/^\/(concierge|cdn-cgi|\.well-known|brand|fonts|assets|images)\//;
    if (clean && !pathname.includes('//') && !keep.test(pathname) && clean!=='/404') {
      const target=clean==='/'?'index.html':clean.slice(1)+'.html';
      try {
        const real=await fs.realpath(path.resolve(root,target));
        if (real.startsWith(root+'/') && (await fs.stat(real)).isFile())
          return new Response(null,{status:301,headers:{Location:clean+new URL(request.url).search}});
      } catch {}
    }
  }
  const relative=pathname==='/'?'index.html':pathname.replace(/^\//,'');
  let file,stat;
  if (!gone) for (const candidate of [relative,relative+'.html',path.join(relative,'index.html')]) {
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
  if(gone)status=410;
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
// Cloudflare Bot Fight Mode injects an inline JavaScript Detections script into every HTML page. Our CSP has no
// 'unsafe-inline' (and must not), so that script was blocked. Cloudflare copies a CSP nonce from the response
// header onto the scripts it injects, so each HTML response gets a fresh random nonce in script-src. The site
// itself has no inline scripts, so nothing else uses it. HTML is not cached at Cloudflare (cf-cache-status DYNAMIC).
function withCspNonce(headers) {
  const type=headers['content-type']||'';
  const csp=headers['content-security-policy'];
  if (!type.startsWith('text/html') || !csp || !/(^|;)\s*script-src\s/.test(csp)) return headers;
  const nonce=randomBytes(16).toString('base64');
  headers['content-security-policy']=csp.replace(/((?:^|;)\s*script-src\s[^;]*)/, `$1 'nonce-${nonce}'`);
  return headers;
}
http.createServer(async(incoming,outgoing)=>{
  try {
    let size=0;const body=[];
    for await(const chunk of incoming){size+=chunk.length;if(size>1048576){outgoing.writeHead(413).end();return;}body.push(chunk);}
    const method=incoming.method;
    const request=new Request('https://'+incoming.headers.host+incoming.url,{method,headers:incoming.headers,
      ...(method!=='GET'&&method!=='HEAD'?{body:Buffer.concat(body)}:{})});
    // The website serves no /api/* routes. They belong to the FastAPI app (in git) and the gateway sends them
    // there. The legacy worker file below is not in git: letting it answer /api/* is how /api/robots broke
    // silently, and how site-check and security-check came to depend on an untracked file. verify-deploy.sh
    // probes this container to prove it stays 404.
    const apiPath=new URL(request.url).pathname;
    if (apiPath==='/api' || apiPath.startsWith('/api/')) {
      outgoing.writeHead(404,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Trendi-Served-By':'website'})
        .end(JSON.stringify({error:'not_found',message:'No such API route on the website.'}));
      return;
    }
    const response=await worker.fetch(request,{PAGESPEED_API_KEY:process.env.PAGESPEED_API_KEY,ASSETS:{fetch:asset}},{waitUntil:promise=>promise.catch(()=>{})});
    outgoing.writeHead(response.status,withCspNonce(Object.fromEntries(response.headers)));
    if(method==='HEAD'||!response.body)outgoing.end();
    else Readable.fromWeb(response.body).pipe(outgoing);
  }catch{
    outgoing.writeHead(502,{'Content-Type':'text/plain'}).end('Website temporarily unavailable');
  }
}).listen(8080,'0.0.0.0');
