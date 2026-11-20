"""Accountant CSV export exact wire parity; no mail/provider connections."""
import csv
import io

def verify(py,rs,db,sql,request):
    auth='Bearer product-owner';base='/owner/reports/export.csv'
    # Distinct tenant fixtures must produce separate exports.
    for query in ('','?days=0','?days=-1','?days=365','?days=9999','?days=bad','?days=1.5'):
        a=request(py,base+query,auth);b=request(rs,base+query,auth)
        assert a==b,(query,a,b)
        if a[0]==200:
            rows=list(csv.reader(io.StringIO(a[1])))
            assert rows[0]==['section','stage_or_status','channel','lost_reason','count','value_cents']
            assert all(len(r)==6 for r in rows),rows
    a=request(py,base,'Bearer product-viewer');b=request(rs,base,'Bearer product-viewer');assert a==b,(a,b)
    foreign=request(rs,base,'Bearer product-foreign')
    assert foreign==request(py,base,'Bearer product-foreign'),foreign
    assert '999999999' in foreign[1] and '18446744073709551614' not in foreign[1],foreign
    for server in (py,rs):
        assert request(server,base,None)[0]==401
    print('PASS: exact Python/Rust accountant CSV export, day bounds, validation, roles and tenant isolation')
