"""Real pipeline and provider-free daily/weekly digest comparisons."""
import json
import socket
import subprocess
import sys
import time
from datetime import datetime,timezone
from pathlib import Path

def verify(py,rs,db,sql,request,environment,binary,work):
    owner='Bearer product-owner'
    for role in ('owner','editor','viewer','foreign'):
        a=request(py,'/owner/crm/pipeline','Bearer product-'+role);b=request(rs,'/owner/crm/pipeline','Bearer product-'+role)
        assert a==b,(role,a,b)
    tid=sql(db,"SELECT id FROM tenants WHERE slug='alpha'")
    ids=sql(db,f"INSERT INTO leads(tenant_id,name,status,score,value_cents) VALUES('{tid}','wide-pipeline','new',100,9223372036854775807),('{tid}','wide-pipeline','new',100,9223372036854775807) RETURNING id").splitlines()
    a=request(py,'/owner/crm/pipeline',owner);b=request(rs,'/owner/crm/pipeline',owner)
    assert a==b and a[1]['open_value_cents']>2**63,(a,b)
    sql(db,"DELETE FROM leads WHERE id IN ("+','.join("'"+i+"'" for i in ids)+")")
    root=Path(__file__).resolve().parents[2];env={**environment,'PYTHONPATH':str(root/'api')+':'+environment['PYTHONPATH']}
    def run(args):
        p=subprocess.run(args,cwd=work,env=env,capture_output=True,text=True,timeout=20)
        assert p.returncode==0,(args,p.stdout,p.stderr)
        return int(p.stdout.strip())
    tid=sql(db,"INSERT INTO tenants(slug,name,public_key,notify_email,weekly_digest,daily_summary,timezone,lead_value_cents,sla_minutes,sla_min_score) VALUES('digest-fixture','Digest fixture','digest-fixture','owner@example.test',true,true,'UTC',15000,30,0) RETURNING id")
    for status,value,age in [('new',2**63-1,2),('new',2**63-1,2),('contacted',0,3),('booked',10000,4),('won',20000,1),('lost',1000,8)]:
        lid=sql(db,f"INSERT INTO leads(tenant_id,name,status,score,score_label,value_cents,created_at,won_at) VALUES('{tid}','Fixture {status}','{status}',80,'hot',{value},now()-interval '{age} hours',now()-interval '1 hour') RETURNING id")
        sql(db,f"INSERT INTO lead_events(lead_id,tenant_id,from_status,to_status) VALUES('{lid}','{tid}','new','{status}')")
    sql(db,f"INSERT INTO tasks(tenant_id,title,due_at) VALUES('{tid}','Overdue fixture',now()-interval '90 minutes')")
    def snapshot():return json.loads(sql(db,f"SELECT coalesce(json_agg(r ORDER BY dedupe_key),'[]') FROM (SELECT kind,channel,to_addr,subject,body,dedupe_key,status FROM outbox WHERE tenant_id='{tid}') r"))
    for clock,expected in [('2026-11-23T07:00:00Z',1),('2026-11-23T08:00:00Z',2),('2026-11-23T20:59:59Z',1),('2026-11-23T21:00:00Z',0),('2026-11-24T08:00:00Z',1),('2027-01-01T08:00:00Z',1),('2026-12-28T08:00:00Z',2)]:
        code="import asyncio;from datetime import datetime;from app import db,sales\nasync def check():\n await db.init();now=datetime.fromisoformat("+repr(clock)+");print(await sales.check_digests(now)+await sales.check_daily_summaries(now));await db.close()\nasyncio.run(check())"
        results=[]
        for command in ([sys.executable,'-c',code],[str(binary),'--check-summaries-once','--at',clock]):
            sql(db,f"DELETE FROM outbox WHERE tenant_id='{tid}'")
            assert run(command)==expected,(clock,expected)
            results.append(snapshot());assert len(results[-1])==expected
            assert all(r['status']=='pending' for r in results[-1])
            assert run(command)==0,'duplicate digest queued'
        assert results[0]==results[1],(clock,results)
    # A quiet day skips the daily note; the weekly summary still exists.
    sql(db,f"DELETE FROM outbox WHERE tenant_id='{tid}';DELETE FROM tasks WHERE tenant_id='{tid}';DELETE FROM leads WHERE tenant_id='{tid}';UPDATE tenants SET sla_minutes=0 WHERE id='{tid}'")
    assert run([str(binary),'--check-summaries-once','--at','2026-11-23T08:00:00Z'])==1
    assert len(snapshot())==1 and snapshot()[0]['dedupe_key'].startswith('digest:')
    sql(db,f"DELETE FROM outbox WHERE tenant_id='{tid}';UPDATE tenants SET notify_email='invalid' WHERE id='{tid}'")
    assert run([str(binary),'--check-summaries-once','--at','2026-11-23T08:00:00Z'])==0
    # Exercise actual enabled startup at local 8am, then graceful shutdown.
    offset=(8-datetime.now(timezone.utc).hour+12)%24-12
    tz='Etc/GMT'+('+' if offset<0 else '-')+str(abs(offset)) if offset else 'UTC'
    sql(db,f"UPDATE tenants SET notify_email='owner@example.test',timezone='{tz}' WHERE id='{tid}';INSERT INTO leads(tenant_id,name) VALUES('{tid}','Live sweep fixture')")
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    worker=subprocess.Popen([str(binary)],cwd=work,env={**env,'OUTBOX_ENABLED':'true','DIGEST_POLL_SECONDS':'3600','BIND':f'127.0.0.1:{port}'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        for _ in range(100):
            assert worker.poll() is None
            if any(r['dedupe_key'].startswith('daily:') for r in snapshot()):break
            time.sleep(.05)
        else:raise AssertionError('digest worker did not perform startup sweep')
        assert all(r['status']=='pending' for r in snapshot())
    finally:
        worker.terminate()
        try:out,err=worker.communicate(timeout=5)
        except subprocess.TimeoutExpired:worker.kill();worker.communicate();raise AssertionError('digest worker failed to stop')
        assert worker.returncode==0,(worker.returncode,err)
    sql(db,f"DELETE FROM tenants WHERE id='{tid}'")
    print('PASS: exact Python/Rust pipeline and wide sums; daily/weekly summary content, local-time boundaries, ISO weeks, quiet days, deduplication, immediate worker startup and graceful stop; nothing sent')
