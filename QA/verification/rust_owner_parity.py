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
    result = subprocess.run(["psql", database, "-X", "-v", "ON_ERROR_STOP=1", "-At", "-c", statement], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(port_number, path, token=None, method="GET"):
    headers = {} if token is None else {"Authorization": token}
    req = urllib.request.Request(f"http://127.0.0.1:{port_number}{path}", headers=headers, method=method)
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
                   "STATIC_DIR": str(ROOT / "api/static")}
    sql(BASE, f'CREATE DATABASE "{NAME}"')
    try:
        with tempfile.TemporaryDirectory(prefix="concierge-owner-parity-") as work, tempfile.TemporaryFile(mode="w+") as log:
            try:
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
