// Run the website's existing Cloudflare worker locally without changing its code.
import http from 'node:http';
import worker from './worker.mjs';

const paths = new Set(['/api/robots', '/api/site-check', '/api/security-check']);
http.createServer(async (incoming, outgoing) => {
  try {
    const url = new URL(incoming.url, `http://${incoming.headers.host}`);
    if (!paths.has(url.pathname)) { outgoing.writeHead(404).end(); return; }
    const chunks = [];
    let size = 0;
    for await (const chunk of incoming) {
      size += chunk.length;
      if (size > 65536) { outgoing.writeHead(413).end(); return; }
      chunks.push(chunk);
    }
    const method = incoming.method;
    const request = new Request(url, {
      method, headers: incoming.headers,
      ...(method !== 'GET' && method !== 'HEAD' ? {body: Buffer.concat(chunks)} : {}),
    });
    const response = await worker.fetch(request, {
      ASSETS: {fetch: req => fetch('http://web' + new URL(req.url).pathname)},
    }, {waitUntil: promise => promise.catch(() => {})});
    outgoing.writeHead(response.status, Object.fromEntries(response.headers));
    outgoing.end(Buffer.from(await response.arrayBuffer()));
  } catch {
    outgoing.writeHead(502, {'content-type': 'application/json'});
    outgoing.end(JSON.stringify({error: 'Website checker unavailable'}));
  }
}).listen(8080, '0.0.0.0');
