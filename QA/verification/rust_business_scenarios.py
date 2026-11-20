"""Tenant settings, monetary summaries and write-role HTTP parity."""
def verify(py,rs,db,sql,request):
    auth='Bearer product-owner'
    tid=sql(db,"SELECT id FROM tenants WHERE slug='alpha'")
    sql(db,f"INSERT INTO quotations(tenant_id,title,status,total_cents,currency,lines,contact,tax_basis_points,subtotal_cents,tax_cents) VALUES('{tid}','Rust summary overflow','accepted',9223372036854775807,'NZD','[]','{{}}',0,9223372036854775807,0),('{tid}','Rust summary overflow','accepted',9223372036854775807,'NZD','[]','{{}}',0,9223372036854775807,0)")
    business={'name':'  Business name  ','gst_number':' GST ','nzbn':' NZBN ','business_address':' Address ','business_phone':' +64212345678 ','quote_terms':' Terms ','quote_valid_days':45,'allow_deposit':False,'deposit_percent':0,'invoice_payment_terms_days':30}
    for path in ('/owner/business','/owner/payment-settings'):
        for token in (auth,'Bearer product-viewer','Bearer product-foreign'):
            a=request(py,path,token);b=request(rs,path,token);assert a==b,(path,a,b)
    for server in (py,rs):
        assert request(server,'/owner/business','Bearer product-viewer','PUT',business)[0]==403
        saved=request(server,'/owner/business','Bearer product-editor','PUT',business)
        assert saved[0]==200 and saved[1]['name']=='Business name' and saved[1]['deposit_percent']==0,saved
    cases=[('/owner/business',{}),('/owner/business',dict(business,quote_valid_days=0)),('/owner/business',dict(business,extra=True)),('/owner/payment-settings',{'url':'ftp://example.test'}),('/owner/payment-settings',{'url':False})]
    for path,body in cases:
        a=request(py,path,auth,'PUT',body);b=request(rs,path,auth,'PUT',body);assert a==b,(path,a,b)
    payment={'instructions':' Pay by bank \u2003','url':' HTTPS://example.test/pay '}
    for server in (py,rs):
        assert request(server,'/owner/payment-settings','Bearer product-editor','PUT',payment)[0]==403
        assert request(server,'/owner/payment-settings',auth,'PUT',payment)[1]=={'ok':True}
        value=request(server,'/owner/payment-settings',auth)
        assert value[1]['instructions']=='Pay by bank' and value[1]['url']=='HTTPS://example.test/pay',value
        assert value[1]['summary']['outstanding_cents']>=18446744073709551614,value
    assert request(py,'/owner/payment-settings',auth)==request(rs,'/owner/payment-settings',auth)
    sql(db,f"DELETE FROM quotations WHERE tenant_id='{tid}' AND title='Rust summary overflow'")
    print('PASS: Python/Rust business and payment settings, role enforcement, tenant isolation and bigint aggregate summaries')
