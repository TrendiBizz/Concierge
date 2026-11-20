"""Run canonical and Rust SLA sweeps on identical disposable rows; no sender runs."""
import json
import subprocess
import sys
import socket
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

def verify(db,sql,environment,binary,work):
    root=Path(__file__).resolve().parents[2]
    env={**environment,'PYTHONPATH':str(root/'api')+':'+environment['PYTHONPATH']}
    def run(args):
        p=subprocess.run(args,cwd=work,env=env,text=True,capture_output=True,timeout=20)
        assert p.returncode==0,(args,p.stdout,p.stderr)
        return int(p.stdout.strip())
    tid=sql(db,"INSERT INTO tenants(slug,name,public_key,notify_email,sla_minutes,sla_min_score,timezone) VALUES('sla-fixture','SLA fixture','sla-fixture','owner@example.test',30,70,'Pacific/Auckland') RETURNING id")
    cid=sql(db,f"INSERT INTO customer_cases(tenant_id,case_key,automation_paused) VALUES('{tid}','sla-paused',true) RETURNING id")
    for label,score,age,status in [('eligible',90,'90 minutes','new'),('low',10,'91 minutes','new'),('old',90,'3 days','new'),('young',90,'2 minutes','new'),('contacted',90,'90 minutes','contacted'),('opted',90,'90 minutes','new'),('paused',90,'90 minutes','new'),('booked',90,'90 minutes','new'),('alerted',90,'90 minutes','new')]:
        lid=sql(db,f"INSERT INTO leads(tenant_id,name,email,score,score_label,created_at,status,message) VALUES('{tid}','{label}','{label}@example.test',{score},'hot',now()-interval '{age}', '{status}','Local request') RETURNING id")
        if label=='paused':sql(db,f"UPDATE leads SET case_id='{cid}' WHERE id='{lid}'")
        if label=='alerted':sql(db,f"UPDATE leads SET sla_alerted_at=now() WHERE id='{lid}'")
        if label=='opted':sql(db,f"INSERT INTO opt_outs(tenant_id,contact) VALUES('{tid}','opted@example.test')")
        if label=='booked':sql(db,f"INSERT INTO appointments(tenant_id,lead_id,starts_at,ends_at) VALUES('{tid}','{lid}',now()+interval '1 day',now()+interval '1 day 1 hour')")
    code="import asyncio;from app import db,sla\nasync def check():\n await db.init();print(await sla.check_once());await db.close()\nasyncio.run(check())"
    def snapshot(tz):
        raw=sql(db,f"SELECT coalesce(json_agg(r ORDER BY name),'[]') FROM (SELECT l.name,o.kind,o.channel,o.to_addr,o.subject,o.body,o.dedupe_key,o.status,o.send_at FROM outbox o JOIN leads l ON l.id=o.lead_id WHERE o.tenant_id='{tid}') r")
        data=json.loads(raw)
        for row in data:
            when=datetime.fromisoformat(row.pop('send_at'));local=when.astimezone(ZoneInfo(tz))
            assert 8<=local.hour<21,local
        return data
    for score,tz,notify,expected in [(70,'Pacific/Auckland','owner@example.test',1),(0,'UTC','owner@example.test',2),(0,'America/New_York','owner@example.test',2),(70,'UTC','invalid-address',0)]:
        sql(db,f"UPDATE tenants SET sla_min_score={score},timezone='{tz}',notify_email='{notify}' WHERE id='{tid}'")
        outcomes=[]
        for command in ([sys.executable,'-c',code],[str(binary),'--check-sla-once']):
            sql(db,f"DELETE FROM outbox WHERE tenant_id='{tid}';UPDATE leads SET sla_alerted_at=CASE WHEN name='alerted' THEN now() ELSE NULL END WHERE tenant_id='{tid}'")
            count=run(command);assert count==expected,(score,tz,count)
            outcomes.append(snapshot(tz))
            assert len(outcomes[-1])==expected
            assert run(command)==0,'already alerted leads were requeued'
        assert outcomes[0]==outcomes[1],(score,tz,outcomes)
    sql(db,f"UPDATE tenants SET sla_minutes=0,notify_email='owner@example.test' WHERE id='{tid}';UPDATE leads SET sla_alerted_at=NULL WHERE tenant_id='{tid}'")
    assert run([str(binary),'--check-sla-once'])==run([sys.executable,'-c',code])==0
    sql(db,f"UPDATE tenants SET sla_minutes=30,sla_min_score=70 WHERE id='{tid}';DELETE FROM outbox WHERE tenant_id='{tid}';UPDATE leads SET sla_alerted_at=CASE WHEN name='alerted' THEN now() ELSE NULL END WHERE tenant_id='{tid}'")
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    worker=subprocess.Popen([str(binary)],cwd=work,env={**env,'OUTBOX_ENABLED':'true','SLA_POLL_SECONDS':'3600','BIND':f'127.0.0.1:{port}'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        for _ in range(100):
            assert worker.poll() is None,'SLA server exited before first sweep'
            if sql(db,f"SELECT count(*) FROM outbox WHERE tenant_id='{tid}'")=='1':break
            time.sleep(.05)
        else:raise AssertionError('enabled SLA worker did not sweep immediately')
        assert sql(db,f"SELECT string_agg(status,',') FROM outbox WHERE tenant_id='{tid}'")=='pending'
    finally:
        worker.terminate()
        try:out,err=worker.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill();worker.communicate();raise AssertionError('SLA worker did not stop on SIGTERM')
        assert worker.returncode==0,(worker.returncode,err)
    sql(db,f"DELETE FROM tenants WHERE id='{tid}'")
    print('PASS: exact Python/Rust SLA sweep/notification parity, opt-out/takeover/booking/age/status exclusions, thresholds, timezone windows, disabled/bad-email gates and deduplication; nothing sent')
