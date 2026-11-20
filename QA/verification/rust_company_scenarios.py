"""Company tenant, role and null-parent regression scenarios, disposable DB only."""
from datetime import datetime

def verify(py,rs,db,sql,request):
    auth='Bearer product-owner'
    normalised=[]
    for server in (py,rs):
        parent=request(server,'/owner/companies',auth,'POST',{'name':' Parent ','domain':' example.test ','notes':' note '})
        child=request(server,'/owner/companies',auth,'POST',{'name':'Child'})
        assert parent[0]==child[0]==201,(parent,child)
        pid,cid=parent[1]['id'],child[1]['id'];path=f'/owner/companies/{cid}'
        assert parent[1]['name']=='Parent' and parent[1]['domain']=='example.test'
        assert request(server,'/owner/companies',auth,'POST',{'name':'Parent'})[0]==409
        assert request(server,path,'Bearer product-foreign','PATCH',{'notes':'wrong'})[0]==404
        assert request(server,path,'Bearer product-viewer','PATCH',{'notes':'wrong'})[0]==403
        nested=request(server,path,'Bearer product-editor','PATCH',{'parent_id':pid})
        assert nested[0]==200 and nested[1]['parent_id']==pid,nested
        unrelated=request(server,path,auth,'PATCH',{'name':None})
        assert unrelated[0]==400,unrelated
        unnested=request(server,path,auth,'PATCH',{'parent_id':None,'notes':'changed'})
        assert unnested[0]==200 and unnested[1]['parent_id'] is None,unnested
        assert request(server,path,auth,'PATCH',{'parent_id':'bad'})[0]==400
        assert request(server,path,'Bearer product-editor','DELETE')[0]==403
        listed=request(server,'/owner/companies','Bearer product-viewer')
        assert listed[0]==200 and any(c['id']==cid and c['contacts']==0 and c['open_value_cents']==0 for c in listed[1]),listed
        row=unnested[1]
        for field in ['created_at','updated_at']:
            assert datetime.fromisoformat(row.pop(field)).tzinfo is not None
        row.pop('id');normalised.append(row)
        assert request(server,path,'Bearer product-foreign','DELETE')[0]==404
        assert request(server,path,auth,'DELETE')[1]=={'deleted':True}
        assert request(server,f'/owner/companies/{pid}',auth,'DELETE')[1]=={'deleted':True}
    assert normalised[0]==normalised[1],normalised
    for body in [{},{'name':False},{'name':'x'*201},{'name':'x','domain':None}]:
        a=request(py,'/owner/companies',auth,'POST',body);b=request(rs,'/owner/companies',auth,'POST',body);assert a==b,(body,a,b)
    print('PASS: Python/Rust company CRUD, nesting/un-nesting, duplicate names, validation and tenant/role isolation')
