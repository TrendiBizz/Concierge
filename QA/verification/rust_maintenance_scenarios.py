"""Canonical maintenance/CLI comparisons and retention effects on disposable rows."""
import json
import subprocess
import sys
from pathlib import Path

def verify(db,sql,environment,binary,work):
    root=Path(__file__).resolve().parents[2]
    env={**environment,'PYTHONPATH':str(root/'api')+':'+environment['PYTHONPATH']}
    def run(args):
        p=subprocess.run(args,cwd=work,env=env,text=True,capture_output=True,timeout=20)
        assert p.returncode==0,(args,p.stderr)
        return p.stdout
    tid=sql(db,"SELECT id FROM tenants WHERE slug='alpha'")
    uid=sql(db,"SELECT id FROM tenant_users WHERE email='product-owner@example.test'")
    sql(db,f"INSERT INTO tenant_sessions(user_id,token_hash,expires_at) SELECT '{uid}','maintenance-'||i,now()-interval '1 day' FROM generate_series(1,3) i")
    sql(db,f"INSERT INTO tenant_invites(tenant_id,email,role,purpose,token_hash,expires_at) SELECT '{tid}','maintenance@example.test','viewer','invite','maintenance-invite-'||i,now()-interval '1 day' FROM generate_series(1,3) i")
    sql(db,"INSERT INTO owner_login_limits(key_hash,attempts,window_until) SELECT 'maintenance-limit-'||i,1,now()-interval '1 day' FROM generate_series(1,3) i")
    before={t:int(sql(db,f'SELECT count(*) FROM {t}')) for t in ('tenant_sessions','tenant_invites','owner_login_limits')}
    py=json.loads(run([sys.executable,'-m','app.owner_maintenance','--batch-size','2']))
    rs=json.loads(run([str(binary),'--prune-owner-auth','--batch-size','2']))
    assert py==rs and all(n==2 for n in rs['eligible'].values()),(py,rs)
    assert before=={t:int(sql(db,f'SELECT count(*) FROM {t}')) for t in before}
    applied=json.loads(run([str(binary),'--prune-owner-auth','--batch-size','2','--apply']))
    assert applied['eligible']==rs['eligible']
    assert all(int(sql(db,f'SELECT count(*) FROM {t}'))==n-2 for t,n in before.items())
    assert sql(db,"SELECT count(*) FROM tenant_sessions WHERE token_hash=encode(sha256('product-owner'::bytea),'hex')")=='1'
    invalid=subprocess.run([str(binary),'--prune-owner-auth','--batch-size','0'],cwd=work,env=env,capture_output=True)
    assert invalid.returncode==2
    no_db=subprocess.run([str(binary),'--prune-owner-auth'],cwd=work,env={k:v for k,v in env.items() if k!='DATABASE_URL'},capture_output=True)
    assert no_db.returncode==2
    conv=sql(db,f"INSERT INTO conversations(tenant_id,session_id) VALUES('{tid}','retention-fixture') RETURNING id")
    def seed():
        sql(db,f"DELETE FROM voice_sessions WHERE conversation_id='{conv}'")
        for label,days in [('old',31),('current',1)]:
            sid=sql(db,f"INSERT INTO voice_sessions(tenant_id,conversation_id,token_hash,created_at) VALUES('{tid}','{conv}','retention-{label}',now()-interval '{days} days') RETURNING id")
            sql(db,f"INSERT INTO voice_recordings(session_id,tenant_id,conversation_id,mime_type,audio,sha256,created_at) VALUES('{sid}','{tid}','{conv}','audio/wav','test','digest',now()-interval '{days} days')")
            for share,delta in [('expired','-1 hour'),('valid','1 hour')]:
                sql(db,f"INSERT INTO voice_recording_shares(token_hash,session_id,tenant_id,expires_at) VALUES('retention-{label}-{share}','{sid}','{tid}',now()+interval '{delta}')")
    def snapshot():
        return [sql(db,"SELECT string_agg(token_hash,',' ORDER BY token_hash) FROM voice_sessions WHERE token_hash LIKE 'retention-%'"),sql(db,"SELECT string_agg(token_hash,',' ORDER BY token_hash) FROM voice_recording_shares WHERE token_hash LIKE 'retention-%'"),sql(db,f"SELECT count(*) FROM voice_recordings WHERE conversation_id='{conv}'")]
    seed()
    run([str(binary),'--purge-voice-once']);rs=snapshot()
    seed()
    code="import asyncio;from app import db,voice_records\nasync def check():\n await db.init();await voice_records.purge_expired();await db.close()\nasyncio.run(check())"
    run([sys.executable,'-c',code]);py=snapshot()
    assert py==rs==['retention-current','retention-current-valid','1'],(py,rs)
    print('PASS: Python/Rust bounded maintenance dry-run parity, apply bounds, active-session preservation and voice retention/cascades')
