#!/usr/bin/env python3
"""Probe every owner-facing GET route on a live box with a real session.

This exists because 976 unit tests passed while `GET /owner/contacts` returned 500 in
production: no test ever ran the SQL against a real schema, and the query ordered by a select
alias inside COALESCE, which Postgres rejects at prepare time. A route is only proven by being
called.

Run it on the box it is checking (it mints a session through the admin API on localhost and
never prints a token):

    scp scripts/verify/probe_owner_routes.py root@host:/tmp/
    ssh root@host 'python3 /tmp/probe_owner_routes.py'

Exit code is 1 when any route answers 5xx, so it can gate a deploy.

"""
import json, re, subprocess, urllib.request, urllib.error

API, SLUG = "http://127.0.0.1:8000", "trendi-meta-review"
ROUTES = json.load(open("/tmp/owner_routes.json"))

def psql(sql):
    r = subprocess.run(["docker","exec","-i","trendi-postgres-1","sh","-c",
        'psql -U "$POSTGRES_USER" -d concierge -At'],
        input=sql, capture_output=True, text=True)
    return r.stdout.strip()

TABLES = ["contacts","leads","cases","quotes","bookings","designs","products","media_assets",
          "email_drafts","knowledge_documents","tasks","email_suppressions","conversations",
          "tenant_users","invoices","social_posts","products_page","voice_calls"]
VALUES = {"slug": SLUG, "address": "nobody@example.invalid"}
for t in TABLES:
    try:
        v = psql(f"select id from {t} limit 1;").splitlines()
        if v and v[0] and not v[0].lower().startswith("error"):
            VALUES[t] = v[0]
            VALUES[t.rstrip('s')] = v[0]
            VALUES[t.rstrip('s') + "_id"] = v[0]
    except Exception:
        pass
VALUES.update({"contact_id": VALUES.get("contact"), "lead_id": VALUES.get("lead"),
               "quote_id": VALUES.get("quote"), "design_id": VALUES.get("design"),
               "product_id": VALUES.get("product"), "draft_id": VALUES.get("email_draft"),
               "doc_id": VALUES.get("knowledge_document"), "task_id": VALUES.get("task"),
               "conversation_id": VALUES.get("conversation"), "token": "x"*40})

admin = [l.split("=",1)[1].strip() for l in open("/opt/trendi/shared/api.env") if l.startswith("ADMIN_TOKEN=")][0]
email = psql(f"select email from tenant_users u join tenants t on t.id=u.tenant_id where t.slug='{SLUG}' and u.role='owner' limit 1;")
out = subprocess.run(["curl","-s","-X","POST","-H",f"X-Admin-Token: {admin}","-H","Content-Type: application/json",
    "-d", json.dumps({"email": email}), f"{API}/admin/tenants/{SLUG}/owner-recovery"],
    capture_output=True, text=True).stdout
tok = json.loads(out)["recovery_token"]
req = urllib.request.Request(f"{API}/owner/auth/invite", data=json.dumps({"token": tok}).encode(), method="POST")
req.add_header("Content-Type","application/json")
with urllib.request.urlopen(req, timeout=60) as r:
    at = json.loads(r.read())["access_token"]
print("session obtained:", bool(at))

def fill(path):
    def sub(m):
        name = m.group(1)
        return str(VALUES.get(name, VALUES.get(name + "_id", "x")))
    return re.sub(r"\{([^}]+)\}", sub, path)

bad, empty, ok = [], [], 0
for row in ROUTES:
    if row["method"] != "GET" or row["path"] in ("/owner-ui", "/owner/auth/link"):
        continue
    url = API + fill(row["path"])
    if "{token}" in row["path"] or "callback" in row["path"]:
        continue
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + at)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read()
            ok += 1
            if r.status == 200 and not body.strip():
                empty.append((row["path"], "empty body"))
    except urllib.error.HTTPError as e:
        detail = e.read()[:160].decode(errors="replace")
        if e.code >= 500:
            bad.append((row["method"], row["path"], e.code, detail))
        elif e.code not in (400, 401, 403, 404, 409, 422):
            bad.append((row["method"], row["path"], e.code, detail))
    except Exception as e:
        bad.append((row["method"], row["path"], "EXC", str(e)[:120]))

print(f"\nGET routes ok: {ok}")
print(f"5xx / unexpected: {len(bad)}")
for b in bad: print("  BUG", b)
print(f"empty 200 bodies: {len(empty)}")
for e in empty: print("  EMPTY", e)

import sys
sys.exit(1 if bad else 0)
