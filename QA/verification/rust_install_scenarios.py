"""Assisted installs persist requests and queue notifications without sending."""
import re

def verify(py,rs,db,sql,request):
    results=[]
    for server in (py,rs):
        tid=sql(db,"SELECT id FROM tenants WHERE slug='alpha'")
        sql(db,f"DELETE FROM install_requests WHERE tenant_id='{tid}'")
        for role,body in (('viewer',{}),('owner',{'website':'  https://example.test  ','platform':'unknown','contact_name':'  Local owner  ','contact_phone':'  0211234567  ','note':'  Note  ','ignored':True})):
            created=request(server,'/owner/install-request','Bearer product-'+role,'POST',body)
            assert created[0]==200 and created[1]['status']=='new',created
            rid=created[1]['id']
            foreign=request(server,'/owner/install-requests','Bearer product-foreign')
            assert foreign[0]==200 and all(r['id']!=rid for r in foreign[1]),foreign
            rows=request(server,'/owner/install-requests','Bearer product-editor')
            row=next(r for r in rows[1] if r['id']==rid)
            assert row['platform']=='unsure' and row['handled_at'] is None,row
            queued=sql(db,f"SELECT row_to_json(q) FROM (SELECT kind,channel,to_addr,subject,body,status FROM outbox WHERE dedupe_key='install-request:{rid}') q")
            import json
            queued=json.loads(queued)
            assert queued['kind']=='owner_alert' and queued['channel']=='email' and queued['status']=='pending',queued
            queued['body']=queued['body'].replace(rid,'REQUEST_ID')
            assert queued['to_addr']=='admin@trendibizz.com',queued
            for key in ('id','created_at'):row.pop(key)
            results.append((row,queued))
            sql(db,f"DELETE FROM outbox WHERE dedupe_key='install-request:{rid}'")
        assert request(server,'/owner/install-request','Bearer invalid','POST',{})[0]==401
    assert results[:2]==results[2:],results
    for body in ({'website':False},{'note':None},{'contact_name':'x'*121},{'platform':'x'*31}):
        a=request(py,'/owner/install-request','Bearer product-owner','POST',body);b=request(rs,'/owner/install-request','Bearer product-owner','POST',body);assert a==b,(body,a,b)
    # Each tenant sees at most its newest twenty requests.
    tid=sql(db,"SELECT id FROM tenants WHERE slug='alpha'")
    sql(db,f"INSERT INTO install_requests(tenant_id,website) SELECT '{tid}','local-'||i FROM generate_series(1,25) i")
    a=request(py,'/owner/install-requests','Bearer product-owner');b=request(rs,'/owner/install-requests','Bearer product-owner');assert a==b and len(a[1])==20,(a,b)
    print('PASS: assisted install defaults/normalisation/validation, tenant isolation, viewer access, newest-20 limit and exact durable notification; nothing delivered')
