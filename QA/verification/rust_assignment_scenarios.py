"""Prove assignment references cannot escape the authenticated tenant."""
def verify(py,rs,db,sql,request):
    auth='Bearer product-owner'
    tid=sql(db,"SELECT id FROM tenants WHERE slug='alpha'")
    foreign=sql(db,"SELECT id FROM tenants WHERE slug='beta'")
    member=sql(db,"SELECT id FROM tenant_users WHERE email='product-editor@example.test'")
    outsider=sql(db,"SELECT id FROM tenant_users WHERE email='product-foreign@example.test'")
    company=sql(db,f"INSERT INTO companies(tenant_id,name) VALUES('{tid}','Assignment fixture') RETURNING id")
    outside_company=sql(db,f"INSERT INTO companies(tenant_id,name) VALUES('{foreign}','Foreign assignment fixture') RETURNING id")
    for tenant in [tid,foreign]:
        sql(db,f"INSERT INTO customer_cases(tenant_id,case_key) VALUES('{tenant}','email:assign@example.test'),('{tenant}','email:second@example.test')")
    lead=sql(db,f"INSERT INTO leads(tenant_id,name) VALUES('{tid}','Assignment lead') RETURNING id")
    foreign_lead=sql(db,f"INSERT INTO leads(tenant_id,name) VALUES('{foreign}','Foreign assignment lead') RETURNING id")
    contact='/owner/contacts/email:assign@example.test'
    cases=[(contact+'/company','PUT',{'company_id':company},200),(contact+'/company','PUT',{'company_id':outside_company},404),(contact+'/company','PUT',{'company_id':'bad'},400),(contact+'/company','PUT',{'company_id':None},200),(contact+'/assignee','PUT',{'user_id':member},200),(contact+'/assignee','PUT',{'user_id':outsider},404),(contact+'/assignee','PUT',{'user_id':'bad'},400),(contact+'/assignee','PUT',{'user_id':'unassigned'},200),(f'/owner/crm/leads/{lead}/assignee','PUT',{'user_id':member},200),(f'/owner/crm/leads/{foreign_lead}/assignee','PUT',{'user_id':member},404),('/owner/contacts/bulk-assign','POST',{'case_keys':[' EMAIL:ASSIGN@EXAMPLE.TEST ','email:second@example.test',' '],'user_id':member},200),('/owner/contacts/bulk-assign','POST',{'case_keys':['email:assign@example.test'],'user_id':None},200),('/owner/contacts/bulk-assign','POST',{'case_keys':[]},422)]
    for path,method,body,status in cases:
        a=request(py,path,auth,method,body);b=request(rs,path,auth,method,body)
        assert a==b and a[0]==status,(path,body,a,b)
    for server in [py,rs]:
        assert request(server,contact+'/assignee','Bearer product-viewer','PUT',{'user_id':member})[0]==403
        sql(db,f"UPDATE tenant_users SET active=false WHERE id='{member}'")
        assert request(server,contact+'/assignee',auth,'PUT',{'user_id':member})[0]==404
        sql(db,f"UPDATE tenant_users SET active=true WHERE id='{member}'")
    assert sql(db,f"SELECT count(*) FROM customer_cases WHERE tenant_id='{foreign}' AND (assigned_to IS NOT NULL OR company_id IS NOT NULL)")=='0'
    print('PASS: Python/Rust contact/company/enquiry assignment, bulk updates, clearing, inactive members and foreign reference rejection')
