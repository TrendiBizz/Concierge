"""Owner API boundary regression; disposable PostgreSQL only, no outbound messaging."""
import os

os.environ.update({
    "DATABASE_URL": "postgresql://postgres:test@127.0.0.1:55432/postgres",
    "ADMIN_TOKEN": "isolated-security-admin",
    "OUTBOX_ENABLED": "false",
    "EMAIL_DRAFTS_ENABLED": "false",
})
from fastapi.testclient import TestClient
from app.main import app
from app import db

checks = 0


def check(label, condition):
    global checks
    assert condition, label
    checks += 1
    print("PASS", label)


with TestClient(app) as client:
    blocked_origin = {"Origin": "https://untrusted.example"}
    check("foreign-origin owner UI denied", client.get("/owner-ui", headers=blocked_origin).status_code == 403)
    check("foreign-origin owner login denied", client.post("/owner/auth/login", headers=blocked_origin, json={}).status_code == 403)
    check("foreign-origin owner preflight denied", client.options("/owner/auth/login", headers={
        **blocked_origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }).status_code == 403)
    page = client.get("/owner-ui")
    check("same-origin owner UI served", page.status_code == 200)
    check("owner UI no-store", page.headers.get("cache-control") == "no-store")
    check("owner UI no-referrer", page.headers.get("referrer-policy") == "no-referrer")
    check("owner UI nosniff", page.headers.get("x-content-type-options") == "nosniff")
    check("owner API no-store on auth failure", client.get("/owner/me").headers.get("cache-control") == "no-store")
    payload = {"slug": "unknown", "email": "missing@example.test", "password": "IncorrectLongPassphrase"}
    results = [client.post("/owner/auth/login", json=payload).status_code for _ in range(10)]
    check("eight attempts accepted for verification", results[:8] == [401]*8)
    check("subsequent attempts throttled in shared DB", results[8:] == [429,429])
    count = client.portal.call(lambda: db.pool().fetchval("SELECT count(*) FROM owner_login_limits"))
    check("limiter stores hashed identifiers only", count == 2)
    client.portal.call(lambda: db.pool().execute("DELETE FROM owner_login_limits"))
    check("reset allows clean verification attempt", client.post("/owner/auth/login", json=payload).status_code == 401)

print(f"{checks}/{checks} owner security checks passed")
