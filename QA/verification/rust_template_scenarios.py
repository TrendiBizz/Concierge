"""Saved reply CRUD parity using a disposable database and no outgoing mail."""
from datetime import datetime

def verify(py,rs,db,sql,request):
    auth='Bearer product-owner'; results=[]
    base='/owner/email-templates'
    body={'name':' Reply ','subject':' Hello ','body':'  Keep indentation\n\t\u2003'}
    for server in (py,rs):
        created=request(server,base,auth,'POST',body)
        assert created[0]==201,created
        row=created[1];path=f"{base}/{row['id']}"
        assert row['name']=='Reply' and row['subject']=='Hello' and row['body']=='  Keep indentation',row
        assert request(server,base,auth,'POST',body)[0]==409
        assert request(server,path,'Bearer product-foreign','PATCH',body)[0]==404
        assert request(server,path,'Bearer product-viewer','PATCH',body)[0]==403
        listed=request(server,base,'Bearer product-viewer')
        assert listed[0]==200 and any(r['id']==row['id'] for r in listed[1]),listed
        assert request(server,base,'Bearer product-foreign')[1]==[]
        updated=request(server,path,'Bearer product-editor','PATCH',dict(body,name='Updated'))
        assert updated[0]==200,updated
        result=updated[1]
        for field in ('created_at','updated_at'):
            assert datetime.fromisoformat(result.pop(field)).tzinfo is not None
        result.pop('id');results.append(result)
        assert request(server,path,'Bearer product-viewer','DELETE')[0]==403
        assert request(server,path,'Bearer product-foreign','DELETE')[0]==404
        assert request(server,path,'Bearer product-editor','DELETE')[1]=={'deleted':True}
        assert request(server,path,auth,'DELETE')[0]==404
    assert results[0]==results[1],results
    for bad in ({},{'name':'x','body':''},{'name':False,'body':'x'},{'name':'x'*121,'body':'x'},{'name':'x','body':'x','subject':None}):
        a=request(py,base,auth,'POST',bad);b=request(rs,base,auth,'POST',bad)
        assert a==b,(bad,a,b)
    print('PASS: Python/Rust saved reply CRUD, whitespace, duplicate names, validation, role and tenant isolation')
