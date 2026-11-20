"""Release wire parity and per-user acknowledgement persistence."""
def verify(py,rs,db,sql,request):
    for path in ('/version','/owner/version'):
        for token in (None,'Bearer invalid','Bearer product-owner'):
            a=request(py,path,token);b=request(rs,path,token);assert a==b,(path,a,b)
        for method in ('HEAD','POST','DELETE'):
            assert request(py,path,None,method)==request(rs,path,None,method)
    for server in (py,rs):
        sql(db,"UPDATE tenant_users SET last_seen_version=0 WHERE email LIKE 'product-%@example.test'")
        for role in ('owner','editor','viewer'):
            auth='Bearer product-'+role
            before=request(server,'/owner/release',auth)
            assert before[0]==200 and before[1]['unseen'] is True,before
            seen=request(server,'/owner/release/seen',auth,'POST')
            assert seen[:2]==(200,{'seen':before[1]['version']}),seen
            assert request(server,'/owner/release',auth)[1]=={**before[1],'unseen':False}
            assert request(server,'/owner/release','Bearer product-foreign')[1]['unseen'] is True
            # Never roll a user back if a newer release was already acknowledged.
            sql(db,f"UPDATE tenant_users SET last_seen_version=99 WHERE email='product-{role}@example.test'")
            assert request(server,'/owner/release/seen',auth,'POST')[0]==200
            assert sql(db,f"SELECT last_seen_version FROM tenant_users WHERE email='product-{role}@example.test'")=='99'
    for path,method in (('/owner/release','GET'),('/owner/release/seen','POST')):
        a=request(py,path,'Bearer invalid',method);b=request(rs,path,'Bearer invalid',method);assert a==b,(path,a,b)
    sql(db,"UPDATE tenant_users SET last_seen_version=0 WHERE email LIKE 'product-%@example.test'")
    assert request(py,'/owner/release','Bearer product-viewer')==request(rs,'/owner/release','Bearer product-viewer')
    print('PASS: exact release catalog/version/notice, per-user acknowledgements, role access, tenant isolation and monotonic seen version')
