"""One foreground command owns the local mock server, browser checks and SEO gate.
Only model/database/tenant lookup are replaced; public chat/action handlers are real.
No outbound calls, production data, LLM spend, mail or SMS.
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'api'))
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import uvicorn
from app import a2ui, convo, enquiries
from app.routers import public

OUT = Path.home() / 'Reports/a2ui'
OUT.mkdir(parents=True, exist_ok=True)
saved = []
messages = []
tenant = {'id': 'test-tenant', 'slug': 'trendi-oauth-staging', 'name': 'Concierge'}
async def tenant_for(*args): return tenant
async def conversation(*args): return 'test-conversation'
async def save_message(*args): messages.append(args)
async def capture(*args, **kwargs): saved.append({'text': args[3], 'conversation': kwargs['conversation_id']})
async def stream(*args, **kwargs):
    yield {'type': 'token', 'text': 'You can send a request below, or describe it in chat.'}
    yield {'type': 'done', 'reply': 'You can send a request below, or describe it in chat.'}
async def turn(*args, **kwargs):
    return {'reply': 'Please describe your request in chat.', 'lead_captured':False, 'booking_url':None, 'appointment':None}
public._main = lambda: SimpleNamespace(STATIC_DIR=ROOT/'api/static', _tenant_for=tenant_for, _rate_limit=lambda *args: None)
public.chat_engine.run_turn_stream = stream
public.chat_engine.run_turn = turn
convo.get_or_create = conversation
convo.save_message = save_message
enquiries.capture = capture
app = FastAPI()

@app.get('/api/v1/widget-config')
async def config():
    return {'name':'Concierge', 'accent_color':'#6d28d9', 'cta_text':'Ask Concierge', 'greeting':'How can we help?', 'voice_enabled':False}
@app.get('/api/v1/chat/poll')
async def poll(): return {'messages':[]}
@app.get('/__evidence')
async def evidence(): return {'saved':saved, 'messages':messages}
@app.get('/')
async def homepage(): return await page('index.html')
@app.get('/robots.txt')
async def robots(): return FileResponse(ROOT/'website/robots.txt',media_type='text/plain')
app.include_router(public.router)

@app.get('/{path:path}')
async def page(path: str):
    if path == 'widget-preview':
        return HTMLResponse('<!doctype html><html lang="en"><title>Concierge widget preview</title><body><h1>Concierge widget</h1><script defer src="/widget.js" data-key="test-public-key"></script></body></html>', headers={'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'"})
    target = ROOT/'website'/(path or 'index.html')
    if not target.is_file() and not Path(path).suffix: target = target.with_suffix('.html')
    if not target.is_file() or not target.resolve().is_relative_to(ROOT/'website'):
        return HTMLResponse('Missing page',status_code=404)
    if target.suffix != '.html': return FileResponse(target)
    raw = target.read_text()
    # Map the existing production widget URL to this local transport only.
    raw = raw.replace('https://chat.trendibizz.com/widget.js', '/widget.js')
    # Faithful site script hash CSP, strict style-src. No unsafe-inline / eval.
    import hashlib,base64
    hashes = ["'sha256-"+base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()+"'" for s in re.findall(r'<script\b[^>]*>(.*?)</script>',raw,re.S)]
    csp = "default-src 'self'; script-src 'self' https://www.googletagmanager.com https://static.cloudflareinsights.com "+' '.join(hashes)+"; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; form-action 'self'"
    return HTMLResponse(raw,headers={'Content-Security-Policy':csp})

async def main():
    server = uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=18765,log_level='error',access_log=False))
    async def checks():
        while not server.started: await asyncio.sleep(.02)
        try:
            proc = await asyncio.create_subprocess_exec('node',os.environ.get('A2UI_CHECK_SCRIPT','e2e.mjs'),cwd=ROOT/'tools/a2ui')
            rc = await proc.wait()
            if rc: return rc
            with (OUT/'seo-gate.txt').open('w') as log:
                proc = await asyncio.create_subprocess_exec('bash',str(ROOT/'scripts/seo-gate.sh'),'http://127.0.0.1:18765',stdout=log,stderr=log)
                gate_rc = await proc.wait()
            (OUT/('backend-evidence.json' if os.environ.get('A2UI_CHECK_SCRIPT','e2e.mjs') == 'e2e.mjs' else 'backend-evidence-failure.json')).write_text(json.dumps({'saved':saved,'messages':messages},indent=2))
            print('SEO gate exit:',gate_rc,flush=True)
            return gate_rc
        finally: server.should_exit = True
    result = await asyncio.gather(server.serve(),checks())
    return result[1]
if __name__ == '__main__': sys.exit(asyncio.run(main()))
