"""Unified timeline and human takeover share the same tenant-scoped store."""
from datetime import datetime

def verify(py,rs,db,sql,request):
    auth='Bearer product-owner';tid=sql(db,"SELECT id FROM tenants WHERE slug='alpha'")
    cid=sql(db,f"INSERT INTO customer_cases(tenant_id,case_key,display_name,primary_phone,primary_email) VALUES('{tid}','email:timeline@example.test','Timeline person','+64212345678','timeline@example.test') RETURNING id")
    lead=sql(db,f"INSERT INTO leads(tenant_id,case_id,name,message) VALUES('{tid}','{cid}','Timeline person','Need a quote') RETURNING id")
    sql(db,f"INSERT INTO case_events(tenant_id,case_id,channel,direction,body,occurred_at) VALUES('{tid}','{cid}','email','inbound','First message',now()-interval '1 hour'),('{tid}','{cid}','sms','outbound','Second message',now()),('{tid}','{cid}','custom-channel','inbound','Third message',now())")
    base='/owner/contacts/email:timeline@example.test'
    for query in ('','?limit=1','?limit=0','?limit=501','?limit=bad'):
        a=request(py,base+'/timeline'+query,auth);b=request(rs,base+'/timeline'+query,auth);assert a==b,(query,a,b)
    for server in (py,rs):
        assert request(server,base+'/timeline','Bearer product-foreign')[0]==404
        assert request(server,base+'/timeline','Bearer product-viewer')[0]==200
        assert request(server,base+'/takeover',auth,'PUT',{'paused':True,'reason':' '})[0]==422
        paused=request(server,base+'/takeover','Bearer product-viewer','PUT',{'paused':True,'reason':'Taking over'})
        assert paused[1]=={'paused':True,'case_key':'email:timeline@example.test'},paused
        state=sql(db,f"SELECT automation_paused,takeover_by,takeover_at IS NOT NULL FROM customer_cases WHERE id='{cid}'")
        assert state=='t|product-viewer@example.test: Taking over|t',state
        route=f'/owner/crm/leads/{lead}/takeover'
        assert request(server,route,'Bearer product-foreign','POST',{'paused':False})[0]==404
        resumed=request(server,route,'Bearer product-viewer','POST',{'paused':False})
        assert resumed[1]=={'lead_id':lead,'automation_paused':False,'updated':True},resumed
        assert sql(db,f"SELECT automation_paused,takeover_by,takeover_at IS NULL FROM customer_cases WHERE id='{cid}'")=='f||t'
    for body in ({},{'paused':'bad'},{'paused':True,'reason':False}):
        a=request(py,base+'/takeover',auth,'PUT',body);b=request(rs,base+'/takeover',auth,'PUT',body);assert a==b,(body,a,b)
    orphan=sql(db,f"INSERT INTO leads(tenant_id,name) VALUES('{tid}','No case') RETURNING id")
    a=request(py,f'/owner/crm/leads/{orphan}/takeover',auth,'POST',{'paused':True});b=request(rs,f'/owner/crm/leads/{orphan}/takeover',auth,'POST',{'paused':True});assert a==b and a[0]==409,(a,b)
    print('PASS: Python/Rust timeline, event ordering/labels, enquiry linkage, cross-channel takeover, viewer access and tenant isolation')
