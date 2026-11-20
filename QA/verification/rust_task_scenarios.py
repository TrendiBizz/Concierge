"""Task HTTP behaviour using only disposable fixture accounts."""
from datetime import datetime

def verify(py,rs,db,sql,request):
    owner='Bearer product-owner'
    results=[]
    for server in (py,rs):
        created=request(server,'/owner/tasks',owner,'POST',{'title':'  Local task  ','notes':'notes','due_at':'2026-12-01T09:30:00'})
        assert created[0]==201,created
        row=created[1];tid=row['id'];path=f'/owner/tasks/{tid}'
        assert row['title']=='Local task' and datetime.fromisoformat(row['due_at']).utcoffset().total_seconds()==0,created
        assert request(server,path,'Bearer product-foreign','PATCH',{'title':'wrong'})[0]==404
        assert request(server,path,'Bearer product-foreign','DELETE')[0]==404
        assert request(server,path,'Bearer product-viewer','PATCH',{'title':'wrong'})[0]==403
        assert request(server,'/owner/tasks','Bearer product-viewer','POST',{'title':'wrong'})[0]==403
        assert request(server,'/owner/tasks','Bearer product-owner','POST',{'title':' ','lead_id':'invalid'})[:2]==(400,{'detail':'Invalid lead id'})
        invalid=request(server,path,owner,'PATCH',{'title':None})
        assert invalid[0]==400,invalid
        assert request(server,path,owner,'PATCH',{})[0]==400
        done=request(server,path,'Bearer product-editor','PATCH',{'status':'done'})
        assert done[0]==200 and done[1]['status']=='done' and datetime.fromisoformat(done[1]['completed_at']).tzinfo is not None,done
        done_list=request(server,'/owner/tasks?status=done','Bearer product-viewer')
        assert done_list[0]==200 and any(t['id']==tid for t in done_list[1]),done_list
        reopened=request(server,path,owner,'PATCH',{'status':'open','due_at':None,'notes':'changed'})
        assert reopened[0]==200 and reopened[1]['completed_at'] is None and reopened[1]['due_at'] is None,reopened
        out=reopened[1]
        for field in ['created_at','updated_at']:
            if field in out: assert datetime.fromisoformat(out.pop(field)).tzinfo is not None
        out.pop('id');results.append(out)
        deleted=request(server,path,owner,'DELETE');assert deleted[0]==200 and deleted[1]=={'deleted':True},deleted
        assert request(server,path,owner,'DELETE')[0]==404
    assert results[0]==results[1],results
    for payload in [{},{'title':False},{'title':'x'*201},{'title':'x','notes':None}]:
        a=request(py,'/owner/tasks',owner,'POST',payload);b=request(rs,'/owner/tasks',owner,'POST',payload)
        assert a==b,(payload,a,b)
    for due in ('2026-11-20','2026-11-20T09:30','2026-11-20 09:30:00.1234567+1300',1690000000000.123,-1.1234567,'1e3','2026-02-30'):
        outcomes=[]
        for server in (py,rs):
            result=request(server,'/owner/tasks',owner,'POST',{'title':'Date format fixture','due_at':due})
            if result[0]==201:
                outcomes.append((201,result[1]['due_at']))
                assert request(server,'/owner/tasks/'+str(result[1]['id']),owner,'DELETE')[0]==200
            else:outcomes.append(result)
        assert outcomes[0]==outcomes[1],(due,outcomes)
    print('PASS: Python/Rust task CRUD, validation, timezone handling, roles and tenant isolation')
