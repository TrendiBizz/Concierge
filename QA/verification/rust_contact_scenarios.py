"""Unified contacts, address ownership and last-identity protection on real HTTP."""
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

def verify(py,rs,db,sql,request):
    auth='Bearer product-owner';tid=sql(db,"SELECT id FROM tenants WHERE slug='alpha'")
    cid=sql(db,f"INSERT INTO customer_cases(tenant_id,case_key,display_name,primary_email) VALUES('{tid}','email:address-test@example.test','Address fixture','address-test@example.test') RETURNING id")
    other=sql(db,f"INSERT INTO customer_cases(tenant_id,case_key,display_name) VALUES('{tid}','email:address-other@example.test','Other address fixture') RETURNING id")
    base='/owner/contacts/email:address-test@example.test/addresses'
    def seed():
        sql(db,f"DELETE FROM customer_addresses WHERE case_id IN ('{cid}','{other}')")
        sql(db,f"INSERT INTO customer_addresses(tenant_id,case_id,kind,value) VALUES('{tid}','{cid}','email','address-test@example.test'),('{tid}','{other}','email','taken@example.test')")
    for server in (py,rs):
        seed()
        created=request(server,base,auth,'POST',{'kind':'email','value':' OFFICE@EXAMPLE.TEST ','label':'Work'})
        assert created[0]==201 and created[1]['value']=='office@example.test',created
        aid=created[1]['id'];path=base+'/'+str(aid)
        same=request(server,base,auth,'POST',{'kind':'email','value':'office@example.test','label':''})
        assert same[1]['id']==aid and same[1]['label']=='Work',same
        assert request(server,base,auth,'POST',{'kind':'email','value':'taken@example.test'})[0]==400
        assert request(server,base,'Bearer product-foreign')[0]==404
        assert request(server,base,'Bearer product-viewer','POST',{'kind':'email','value':'x@example.test'})[0]==403
        assert request(server,path,'Bearer product-foreign','DELETE')[0]==404
        assert request(server,path,auth,'DELETE')[1]=={'removed':True}
        assert request(server,path,auth,'DELETE')[0]==400 # last identity cannot be deleted
        listed=request(server,base,'Bearer product-viewer');assert listed[0]==200 and len(listed[1]['addresses'])==1,listed
        assert datetime.fromisoformat(listed[1]['addresses'][0]['created_at']).tzinfo is not None
    seed()
    for query in ('?q=Address%20fixture','?q=absent','?limit=0','?limit=201','?limit=bad'):
        a=request(py,'/owner/contacts'+query,auth);b=request(rs,'/owner/contacts'+query,auth)
        assert a==b,(query,a,b)
    for body in ({},{'kind':'email','value':'bad'},{'kind':'phone','value':'bad'},{'kind':'fax','value':'x'},{'kind':'email','value':None}):
        a=request(py,base,auth,'POST',body);b=request(rs,base,auth,'POST',body);assert a==b,(body,a,b)
    # Rust strengthens the last-identity invariant under simultaneous removals.
    added=request(rs,base,auth,'POST',{'kind':'email','value':'parallel@example.test'})
    ids=[r['id'] for r in request(rs,base,auth)[1]['addresses']]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda i:request(rs,base+'/'+str(i),auth,'DELETE')[0],ids))
    assert sorted(outcomes)==[200,400],outcomes
    assert len(request(rs,base,auth)[1]['addresses'])==1
    print('PASS: Python/Rust contacts search/limits, address ownership, validation, roles and Rust concurrent last-identity protection')
