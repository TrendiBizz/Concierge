"""Run real Python/Rust owner routes against a disposable loopback PostgreSQL.

Uses TEST_DATABASE_URL only as a local administrative test connection; creates
and drops a uniquely named database. Never uses customer rows or sends messages.
Build server-rs first. Python dependencies/shims are the existing API test ones.
"""
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
BASE = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:pw@127.0.0.1:55433/postgres")
URL = urlsplit(BASE)
if URL.hostname not in ("localhost", "127.0.0.1", "::1"):
    raise SystemExit("Refusing a non-loopback test database")
NAME = "concierge_rust_test_" + uuid.uuid4().hex
DB = urlunsplit(URL._replace(path="/" + NAME))
BIN = ROOT / "concierge-stack/server-rs/target/debug/concierge-server"


def sql(database, statement):
    result = subprocess.run(["psql", database, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-At", "-c", statement], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(port_number, path, token=None, method="GET", data=None, extra_headers=None):
    headers = {} if token is None else {"Authorization": token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    headers.update(extra_headers or {})
    req = urllib.request.Request(f"http://127.0.0.1:{port_number}{path}", headers=headers, method=method, data=None if data is None else json.dumps(data).encode())
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        try:
            body = json.loads(raw)
        except ValueError:
            body = raw.decode()
        return response.status, body, {key: response.headers.get(key) for key in (
            "Content-Type", "Cache-Control", "X-Content-Type-Options", "Referrer-Policy", "Allow")}


def wait(port_number, process):
    for _ in range(150):
        assert process.poll() is None, "server exited; see captured server logs"
        try:
            if request(port_number, "/healthz")[0] == 200:
                return
        except OSError:
            pass
        time.sleep(0.1)
    raise AssertionError("server did not become healthy")


def main():
    assert BIN.is_file(), "Build concierge-server before running parity"
    py, rs = port(), port()
    while rs == py:
        rs = port()
    processes = []
    comparisons = 0
    # Do not inherit provider credentials or read the repository's .env file.
    environment = {"PATH": os.environ["PATH"], "PYTHONPATH": str(ROOT / "QA/verification/shims"),
                   "DATABASE_URL": DB, "ADMIN_TOKEN": "local-test-only", "OUTBOX_ENABLED": "false",
                   "SMS_PROVIDER": "none", "PUBLIC_BASE_URL": "http://localhost:8000",
                   "STATIC_DIR": str(ROOT / "api/static"), "ACTION_GATEWAY_ENABLED":"true",
                   "ACTION_GATEWAY_KEY":"local-action-test-key-only"}
    sql(BASE, f'CREATE DATABASE "{NAME}"')
    try:
        with tempfile.TemporaryDirectory(prefix="concierge-owner-parity-") as work, tempfile.TemporaryFile(mode="w+") as log:
            try:
                for _ in range(2):
                    migration=subprocess.run([str(BIN), "--migrate-only"],cwd=work,env=environment,stdout=log,stderr=log,timeout=60)
                    assert migration.returncode==0,"Rust schema migration failed"
                print("PASS: Rust initialises and reapplies the full schema without Python")
                processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(ROOT / "api"), "--host", "127.0.0.1", "--port", str(py)], cwd=work, env=environment, stdout=log, stderr=log))
                wait(py, processes[-1])
                processes.append(subprocess.Popen([str(BIN)], cwd=work, env={**environment, "BIND": f"127.0.0.1:{rs}"}, stdout=log, stderr=log))
                wait(rs, processes[-1])

                def same(label, path, authorization=None, method="GET"):
                    nonlocal comparisons
                    before = datetime.now().astimezone()
                    a, b = request(py, path, authorization, method), request(rs, path, authorization, method)
                    after = datetime.now().astimezone()
                    # The sole ignored value is request time, checked for validity
                    # and the exact reported window instead of erased blindly.
                    for response in (a, b):
                        if response[0] == 200 and isinstance(response[1], dict) and "since" in response[1]:
                            from datetime import timedelta
                            since = datetime.fromisoformat(response[1]["since"])
                            now = since + timedelta(days=response[1]["days"])
                            assert before <= now <= after, (label, "invalid report clock", now)
                            response[1]["since"] = "<request-time>"
                    assert a == b, f"{label}:\nPython {a}\nRust   {b}"
                    comparisons += 1
                    return a

                for slug in ("alpha", "beta", "empty"):
                    sql(DB, f"INSERT INTO tenants(slug,name,public_key) VALUES ('{slug}','{slug}','pk_{slug}')")
                for slug, role in (("alpha", "owner"), ("beta", "viewer"), ("empty", "editor")):
                    sql(DB, f"INSERT INTO tenant_users(tenant_id,email,role,password_hash) SELECT id,'{slug}@example.test','{role}','no-password' FROM tenants WHERE slug='{slug}'")
                    digest = hashlib.sha256(slug.encode()).hexdigest()
                    sql(DB, f"INSERT INTO tenant_sessions(user_id,token_hash,expires_at) SELECT id,'{digest}',now()+interval '1 hour' FROM tenant_users WHERE email='{slug}@example.test'")
                # Current, prior and older periods, unknown channel and foreign
                # tenant values make omission of any SQL predicate observable.
                for slug, days, channel in (("alpha", 2, "phone"), ("alpha", 3, "email"), ("alpha", 40, "sms"), ("alpha", 75, "chat"), ("alpha", 2, "other"), ("beta", 2, "phone")):
                    sql(DB, f"INSERT INTO leads(tenant_id,name,channel,created_at) SELECT id,'fixture','{channel}',now()-interval '{days} days' FROM tenants WHERE slug='{slug}'")
                for slug, days, status, payment, cents, sent in (
                    ("alpha",2,"accepted","paid",10505,True),
                    ("alpha",3,"accepted","declared",25001,True),
                    ("alpha",4,"accepted","unpaid",8800,True),
                    ("alpha",4,"accepted","waived",900,True),
                    ("alpha",5,"draft","paid",700,False),
                    ("alpha",40,"accepted","unpaid",301,True),
                    ("alpha",75,"accepted","paid",999,True),
                    ("beta",2,"accepted","paid",999999999,True)):
                    sent_value = "now()" if sent else "NULL"
                    # Draft paid without confirmation must not count as paid.
                    confirmed = "now()" if payment == "paid" and status == "accepted" else "NULL"
                    sql(DB, f"""INSERT INTO quotations(tenant_id,lead_id,title,currency,status,lines,contact,tax_basis_points,subtotal_cents,tax_cents,total_cents,payment_status,payment_confirmed_at,sent_at,created_at)
                        SELECT t.id,(SELECT id FROM leads WHERE tenant_id=t.id LIMIT 1),'fixture','NZD','{status}','[]','{{}}',0,{cents},0,{cents},'{payment}',{confirmed},{sent_value},now()-interval '{days} days' FROM tenants t WHERE slug='{slug}'""")

                sql(DB,"""INSERT INTO quotations(tenant_id,lead_id,title,currency,status,lines,contact,tax_basis_points,subtotal_cents,tax_cents,total_cents,payment_status,payment_confirmed_at,sent_at)
                    SELECT t.id,(SELECT id FROM leads WHERE tenant_id=t.id LIMIT 1),'overflow-fixture','NZD','accepted','[]','{}',0,9223372036854775807,0,9223372036854775807,'paid',now(),now() FROM tenants t CROSS JOIN generate_series(1,2) WHERE slug='alpha'""")
                overflow=same("revenue aggregate beyond signed bigint", "/owner/revenue", "Bearer alpha")
                assert overflow[0]==200 and overflow[1]["accepted_cents"]>2**64-2,overflow
                sql(DB,"DELETE FROM quotations WHERE title='overflow-fixture'")
                for path in ("/owner/me", "/owner/revenue", "/owner/revenue?days=bad"):
                    for auth in (None,"", "Basic alpha", "Bearer", "Bearer ", "Bearer " + "x"*257, "Bearer unknown", "Bearer  alpha"):
                        same("invalid authentication", path, auth)
                for slug in ("alpha","beta","empty"):
                    same("valid identity", "/owner/me", "bEaReR " + slug)
                    for days in (None,0,1,-1,30,60,365,100000,"bad","1.0","1_0","", "30&days=1"):
                        path = "/owner/revenue" + ("" if days is None else f"?days={days}")
                        same("revenue period " + str(days), path, "Bearer " + slug)
                result = same("recorded paid and outstanding", "/owner/revenue", "Bearer alpha")[1]
                assert result["accepted_cents"] == 45206
                assert result["paid_cents"] == 10505
                assert result["outstanding_cents"] == 33801
                assert result["enquiries"] == 3  # includes the unknown channel
                assert result["quotes_sent"] == 4
                for field, value in (("active","false"),("active","true")):
                    sql(DB, f"UPDATE tenant_users SET {field}={value} WHERE email='alpha@example.test'")
                    same("account activation", "/owner/me", "Bearer alpha")
                sql(DB, "UPDATE tenant_sessions SET expires_at=now()-interval '1 second' WHERE user_id=(SELECT id FROM tenant_users WHERE email='alpha@example.test')")
                same("expired session", "/owner/me", "Bearer alpha")
                same("expired session report", "/owner/revenue", "Bearer alpha")
                sql(DB, "DELETE FROM tenant_sessions WHERE user_id=(SELECT id FROM tenant_users WHERE email='beta@example.test')")
                same("deleted session", "/owner/me", "Bearer beta")
                # ASGI retains trailing optional header whitespace; Hyper removes
                # it before exposing HeaderMap. Record the intentional protocol
                # difference instead of counting it as byte-identical parity.
                assert request(py, "/owner/me", "Bearer empty ")[0] == 401
                assert request(rs, "/owner/me", "Bearer empty ")[0] == 200
                print("KNOWN DIFFERENCE: trailing HTTP header OWS is normalised by Hyper")

                # Real upgrade fixture: audit/approval records survive the legacy
                # table renames; rerunning the complete schema remains idempotent.
                sql(DB, "INSERT INTO case_action_settings(tenant_id,autonomy) SELECT id,'draft_review' FROM tenants WHERE slug='alpha'")
                sql(DB, "INSERT INTO case_action_state(tenant_id,lead_id,automation_paused) SELECT tenant_id,id,true FROM leads LIMIT 1")
                sql(DB, "INSERT INTO case_actions(tenant_id,lead_id,idempotency_key,op,fingerprint,state,result) SELECT tenant_id,id,'upgrade-fixture','escalate_case','fingerprint','done','{\"ok\":true}' FROM leads LIMIT 1")
                snapshots = {}
                pairs = (("hermes_tenant_settings","case_action_settings"),("hermes_case_state","case_action_state"),("hermes_actions","case_actions"))
                for old, new in pairs:
                    snapshots[new] = sql(DB, f"SELECT row_to_json(t)::text FROM {new} t ORDER BY tenant_id")
                    sql(DB, f"ALTER TABLE {new} RENAME TO {old}")
                schema = (ROOT / "api/app/schema.sql").read_text().replace("__DIM__", "384")
                for _ in range(2):
                    sql(DB, schema)
                    for old, new in pairs:
                        assert sql(DB, f"SELECT row_to_json(t)::text FROM {new} t ORDER BY tenant_id") == snapshots[new]
                        assert sql(DB, f"SELECT to_regclass('public.{old}') IS NULL") == "t"
                print("PASS: legacy action state/audit data preserved; full schema reapplied twice")
                # Credential exchanges run against the real DB, with independent
                # fixtures per implementation because they deliberately mutate state.
                for endpoint, payload in (
                    ("login", {}), ("login", {"slug":1,"email":None,"password":False}),
                    ("invite", {}), ("invite", {"token":"short"}),
                    ("invite", {"token":None}),
                    ("redeem", {"token":"short","password":"tiny"}),
                    ("code/verify", {"email":"a@example.test","code":"invalid"}),
                ):
                    a=request(py,"/owner/auth/"+endpoint,method="POST",data=payload)
                    b=request(rs,"/owner/auth/"+endpoint,method="POST",data=payload)
                    assert a==b,(endpoint,payload,a,b)
                    comparisons+=1
                for server in (py,rs):
                    sql(DB,"TRUNCATE owner_login_limits")
                    raw="invitation-"+uuid.uuid4().hex
                    hashed=hashlib.sha256(raw.encode()).hexdigest()
                    sql(DB,f"INSERT INTO tenant_invites(tenant_id,email,role,purpose,token_hash,expires_at) SELECT id,'alpha@example.test','owner','recovery','{hashed}',now()+interval '1 hour' FROM tenants WHERE slug='alpha'")
                    first=request(server,"/owner/auth/invite",method="POST",data={"token":raw})
                    assert first[0]==200,first
                    session=first[1]["access_token"]
                    assert len(session)==43 and first[1]["expires_in"]==2592000
                    assert session not in sql(DB,"SELECT token_hash FROM tenant_sessions")
                    assert request(server,"/owner/me","Bearer "+session)[0]==200
                    again=request(server,"/owner/auth/invite",method="POST",data={"token":raw})
                    assert again[0]==200,again
                    assert request(server,"/owner/me","Bearer "+session)[0]==200,"link reuse revoked existing session"
                    assert request(server,"/owner/auth/logout","Bearer "+session,"POST")[0]==200
                    assert request(server,"/owner/me","Bearer "+session)[0]==401
                    assert request(server,"/owner/me","Bearer "+again[1]["access_token"])[0]==200
                    sql(DB,f"UPDATE tenant_invites SET used_at=now()-interval '31 minutes' WHERE token_hash='{hashed}'")
                    assert request(server,"/owner/auth/invite",method="POST",data={"token":raw})[0]==400
                    # Redeeming a password invitation invalidates old sessions.
                    raw="password-"+uuid.uuid4().hex
                    hashed=hashlib.sha256(raw.encode()).hexdigest()
                    sql(DB,f"INSERT INTO tenant_invites(tenant_id,email,role,purpose,token_hash,expires_at) SELECT id,'alpha@example.test','owner','recovery','{hashed}',now()+interval '1 hour' FROM tenants WHERE slug='alpha'")
                    pwd="a local test password only"
                    redeemed=request(server,"/owner/auth/redeem",method="POST",data={"token":raw,"password":pwd})
                    assert redeemed[0]==200,redeemed
                    assert request(server,"/owner/me","Bearer "+again[1]["access_token"])[0]==401
                    assert request(server,"/owner/auth/redeem",method="POST",data={"token":raw,"password":pwd})[0]==400
                    valid=request(server,"/owner/auth/login",method="POST",data={"slug":"alpha","email":" ALPHA@example.test ","password":pwd})
                    assert valid[0]==200 and valid[1]["expires_in"]==43200,valid
                    assert request(server,"/owner/me","Bearer "+valid[1]["access_token"])[0]==200
                    for n in range(8):
                        fail=request(server,"/owner/auth/login",method="POST",data={"slug":"beta","email":"alpha@example.test","password":pwd})
                        assert fail[0]==(429 if n==7 else 401),fail
                    # Single-use codes serialize concurrent consumers.
                    sql(DB,"TRUNCATE owner_login_limits")
                    code="654321"
                    hashed=hashlib.sha256(code.encode()).hexdigest()
                    sql(DB,f"DELETE FROM tenant_invites WHERE token_hash='{hashed}'; INSERT INTO tenant_invites(tenant_id,email,role,purpose,token_hash,expires_at) SELECT id,'alpha@example.test','owner','code','{hashed}',now()+interval '10 minutes' FROM tenants WHERE slug='alpha'")
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        replies=list(executor.map(lambda _:request(server,"/owner/auth/code/verify",method="POST",data={"email":"alpha@example.test","code":code}),range(2)))
                    assert sorted(reply[0] for reply in replies)==[200,400],replies
                print("PASS: owner credential validation, invite grace, session isolation/revocation, password login, shared throttle and concurrent single-use codes")
                # Restore deterministic sessions after revocation tests and give
                # the same tenant an editor to prove private-cost filtering.
                for account, role, tenant in (("product-owner","owner","alpha"),("product-editor","editor","alpha"),("product-viewer","viewer","alpha"),("product-foreign","owner","beta")):
                    hashed=hashlib.sha256(account.encode()).hexdigest()
                    sql(DB,f"INSERT INTO tenant_users(tenant_id,email,role,password_hash) SELECT id,'{account}@example.test','{role}','no-password' FROM tenants WHERE slug='{tenant}'")
                    sql(DB,f"INSERT INTO tenant_sessions(user_id,token_hash,expires_at) SELECT id,'{hashed}',now()+interval '1 hour' FROM tenant_users WHERE email='{account}@example.test'")
                base_product={"sku":" LOCAL-SKU ","name":" Local product ","sale_price_cents":1200,"cost_price_cents":"300","stock_quantity":5}
                for invalid in ({}, {**base_product,"sale_price_cents":True}, {**base_product,"sale_price_cents":1200.0}, {**base_product,"sale_price_cents":"1200"}, {**base_product,"sku":""}, {**base_product,"untrusted":"x"}, {**base_product,"cost_price_cents":-1}):
                    a=request(py,"/owner/products","Bearer product-owner","POST",invalid)
                    b=request(rs,"/owner/products","Bearer product-owner","POST",invalid)
                    assert a==b,(invalid,a,b)
                    comparisons+=1
                normalised=[]
                for server in (py,rs):
                    created=request(server,"/owner/products","Bearer product-owner","POST",base_product)
                    assert created[0]==201,created
                    item=created[1];pid=item["id"]
                    assert item["sku"]=="LOCAL-SKU" and item["cost_price_cents"]==300
                    for role,status in (("viewer",403),("editor",200),("owner",200)):
                        listed=request(server,"/owner/products","Bearer product-"+role)
                        assert listed[0]==status,listed
                        if status==200:
                            assert ("cost_price_cents" in listed[1][0])==(role=="owner")
                    assert request(server,"/owner/products","Bearer product-editor","POST",base_product)[0]==403
                    assert request(server,"/owner/products/"+pid,"Bearer product-foreign","PUT",base_product)[0]==404
                    assert request(server,"/owner/products/"+pid+"/stock","Bearer product-foreign","POST",{"delta":1})[0]==404
                    assert request(server,"/owner/products/"+pid,"Bearer product-editor","DELETE")[0]==403
                    updated=request(server,"/owner/products/"+pid,"Bearer product-owner","PUT",{**base_product,"name":"Changed"})
                    assert updated[0]==200 and updated[1]["name"]=="Changed",updated
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        replies=list(executor.map(lambda _:request(server,"/owner/products/"+pid+"/stock","Bearer product-editor","POST",{"delta":2,"reason":" restock "}),range(4)))
                    assert all(r[0]==200 and "cost_price_cents" not in r[1] for r in replies),replies
                    assert sql(DB,f"SELECT stock_quantity FROM products WHERE id='{pid}'")=="13"
                    assert sql(DB,f"SELECT count(*) FROM product_stock_movements WHERE product_id='{pid}' AND reason='restock' AND actor='product-editor@example.test'")=="4"
                    deleted=request(server,"/owner/products/"+pid,"Bearer product-owner","DELETE")
                    assert deleted[0]==200 and deleted[1]["active"] is False
                    result=deleted[1]
                    for field in ("created_at","updated_at"):
                        assert datetime.fromisoformat(result.pop(field)).tzinfo is not None
                    result.pop("id")
                    normalised.append(result)
                    sql(DB,f"DELETE FROM products WHERE id='{pid}'")
                assert normalised[0]==normalised[1],normalised
                print("PASS: product validation/CRUD, tenant and role isolation, owner-only costs, concurrent stock updates and audit records")
                from rust_task_scenarios import verify as verify_tasks
                verify_tasks(py,rs,DB,sql,request)
                from rust_action_scenarios import verify
                verify(py,rs,DB,sql,request)
                for path in ("/owner/me","/owner/revenue"):
                    for method in ("HEAD","POST","PUT","DELETE"):
                        same("method boundary", path, "Bearer empty", method)
            except BaseException:
                log.seek(0)
                print(log.read()[-12000:], file=sys.stderr)
                raise
            finally:
                for process in processes:
                    process.terminate()
                for process in processes:
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
    finally:
        sql(BASE, f'DROP DATABASE "{NAME}" WITH (FORCE)')
    print(f"PASS: {comparisons} Python/Rust owner HTTP comparisons; disposable database removed")


if __name__ == "__main__":
    main()
