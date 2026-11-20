"""Inventory mounted Python routes versus registered Rust routes; fail closed for cutover.

A route being registered is not proof of behavioural parity. --require-complete
also requires an explicit verified worker manifest, so a partial server cannot
accidentally become the production replacement.
"""
import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
os.environ.update(DATABASE_URL='postgresql://unused:unused@127.0.0.1:1/unused',ADMIN_TOKEN='local-only',OUTBOX_ENABLED='false')
sys.path[:0]=[str(ROOT/'QA/verification/shims'),str(ROOT/'api')]
from app.main import app

def shape(path):
    return re.sub(r'\{[^}]+\}|:[A-Za-z_][A-Za-z_0-9]*','{}',path)

def rust_routes():
    source=(ROOT/'concierge-stack/server-rs/src/lib.rs').read_text()
    routes=[]
    for m in re.finditer(r'\.route\(\s*"([^"]+)"\s*,',source):
        start=m.end();depth=1;quote=False;escape=False;end=start
        for end in range(start,len(source)):
            ch=source[end]
            if quote:
                if escape:escape=False
                elif ch=='\\':escape=True
                elif ch=='"':quote=False
            elif ch=='"':quote=True
            elif ch=='(':depth+=1
            elif ch==')':
                depth-=1
                if not depth:break
        expr=source[start:end]
        methods=set(re.findall(r'(?:\.|::|\b)(get|post|put|patch|delete|head|options)\s*\(',expr))
        if re.search(r'\bget_(?:only|allow)\(',expr):methods.add('get')
        if 'ws::' in expr:methods={'WEBSOCKET'}
        routes.extend({'method':method.upper(),'path':m[1]} for method in sorted(methods))
    return routes

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--require-complete',action='store_true');parser.add_argument('--output',type=Path,default=ROOT/'QA/verification/rust-migration-inventory.json');args=parser.parse_args()
    rust=rust_routes();keys={(r['method'],shape(r['path'])) for r in rust}
    mounted=[]
    def mounted_routes(routes):
        for route in routes:
            if hasattr(route,'effective_candidates'):
                yield from mounted_routes(route.effective_candidates())
            else:yield route
    for route in mounted_routes(app.routes):
        if route.path in ['/openapi.json','/docs','/docs/oauth2-redirect','/redoc']:continue
        for method in sorted(getattr(route,'methods',None) or ['WEBSOCKET']):
            endpoint=getattr(route,'endpoint',None)
            mounted.append({'method':method,'path':route.path,'source':getattr(endpoint,'__module__',None),'registered_in_rust':(method,shape(route.path)) in keys})
    workers=[]
    for path in sorted((ROOT/'api/app').glob('*.py')):
        tree=ast.parse(path.read_text())
        for n in ast.walk(tree):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='create_task':
                call=ast.unparse(n)
                verified=path.name=='main.py' and call=='asyncio.create_task(maintain_voice_records())'
                workers.append({'source':str(path.relative_to(ROOT)),'line':n.lineno,'call':call,'verified_rust_replacement':verified,'evidence':'QA/verification/rust_maintenance_scenarios.py' if verified else None})
    voice=list((ROOT/'concierge-stack/agent').glob('*.py'))
    missing=[r for r in mounted if not r['registered_in_rust']]
    result={'scope':'Concierge-owned Python services; Hermes removed','cutover_ready':not missing and all(w['verified_rust_replacement'] for w in workers) and not voice,'counts':{'mounted_python_routes':len(mounted),'registered_rust_matches':len(mounted)-len(missing),'missing_rust_routes':len(missing),'python_background_task_sites':len(workers),'unverified_worker_replacements':sum(not w['verified_rust_replacement'] for w in workers),'python_voice_modules':len(voice)},'routes':mounted,'rust_registrations':rust,'background_tasks':workers,'voice_modules':[str(p.relative_to(ROOT)) for p in voice],'limitation':'Registration is not verification. HTTP differential evidence and worker lifecycle verification are required before deployment.'}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['counts']));print('cutover_ready='+str(result['cutover_ready']).lower())
    if args.require_complete and not result['cutover_ready']:raise SystemExit(1)
if __name__=='__main__':main()
