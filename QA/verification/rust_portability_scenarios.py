"""Customer export wire parity and webhook secret/tenant isolation; never delivers."""
import csv
import io

def verify(py,rs,db,sql,request):
    auth='Bearer product-owner';base='/owner/webhooks'
    for query in ('','?format=json','?format=csv','?format=bad'):
        for token in (auth,'Bearer product-viewer','Bearer product-foreign'):
            path='/owner/export/contacts'+query
            a=request(py,path,token);b=request(rs,path,token);assert a==b,(path,a,b)
            if query=='?format=csv':
                rows=list(csv.reader(io.StringIO(a[1])))
                assert rows[0]==['customer','case_key','kind','address','channels','last_seen'] and all(len(r)==6 for r in rows)
    body={'url':'https://example.test/crm ','secret':'local fixture secret'}
    for server in (py,rs):
        request(server,base,auth,'DELETE')
        assert request(server,base,auth)[1]=={'webhook':None}
        assert request(server,base,'Bearer product-editor','POST',body)[0]==403
        assert request(server,base,auth,'POST',body)[1]=={'url':'https://example.test/crm','active':True}
        public=request(server,base,auth)
        assert 'secret' not in public[1]['webhook'],public
        assert request(server,base,'Bearer product-foreign')[1]=={'webhook':None}
        assert request(server,base,'Bearer product-foreign','DELETE')[0]==200
        assert request(server,base,auth)[1]['webhook']['active'] is True
        assert request(server,base,'Bearer product-viewer','DELETE')[0]==403
        assert request(server,base,auth,'DELETE')[1]=={'removed':True}
    for bad in ({},{'url':'http://example.test','secret':'local fixture secret'},{'url':'https://example.test','secret':'short'},{'url':False,'secret':'local fixture secret'}):
        a=request(py,base,auth,'POST',bad);b=request(rs,base,auth,'POST',bad);assert a==b,(bad,a,b)
    print('PASS: exact Python/Rust JSON/CSV customer exports, webhook configuration, secret masking and tenant/role isolation; no webhook delivery')
