"""Differential test: the real Rust server (concierge-server) and the real Python API answer the SAME requests over the SAME PostgreSQL.

Local run (needs Postgres at 127.0.0.1:55432 with the API schema applied by the API itself, a built binary and the API's Python deps):

    cargo build --release --manifest-path concierge-stack/server-rs/Cargo.toml
    PYTHONPATH=QA/verification/shims:api python QA/verification/rust_server_parity.py

Starts two loopback servers, sends nothing anywhere, and removes the rows it creates. Compares status, JSON body, content type and the security headers.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "concierge-stack/server-rs/target/release/concierge-server"
PORT = os.environ.get("CONCIERGE_TEST_POSTGRES_PORT", "55432")
# Parallel runs (several worktrees on one PostgreSQL) must not share a database or ports: the harness deletes every `parity-%` tenant.
DB = f"postgresql://postgres:test@127.0.0.1:{PORT}/{os.environ.get('CONCIERGE_TEST_DB', 'postgres')}"
PY, RS = int(os.environ.get("CONCIERGE_TEST_PY_PORT", "8098")), int(os.environ.get("CONCIERGE_TEST_RS_PORT", "8097"))
ENV = {"DATABASE_URL": DB, "ADMIN_TOKEN": "parity-admin", "PUBLIC_BASE_URL": "http://localhost:8000", "VOICE_RECORDING_ENABLED": "true", "OUTBOX_ENABLED": "false"}
n = 0
KEEP = ("content-type", "cache-control", "x-content-type-options", "referrer-policy", "access-control-allow-origin")


def psql(sql):
    out = subprocess.run(["psql", DB, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def get(port, path, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, body, hdrs = r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        status, body, hdrs = e.code, e.read(), e.headers
    try:
        parsed = json.loads(body) if body else None
    except ValueError:
        parsed = body.decode()
    return status, parsed, {k: hdrs[k] for k in KEEP if hdrs.get(k) is not None}


def wait(port):
    for _ in range(150):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)
            return
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    raise SystemExit(f"server on {port} never became healthy")


def same(label, path, headers=None, normalise=None):
    """The two servers must agree on status, body, content type and security headers."""
    global n
    a, b = get(PY, path, headers), get(RS, path, headers)
    if normalise:
        a, b = normalise(a), normalise(b)
    assert a[0] == b[0], f"{label}: status python={a[0]} rust={b[0]} body={a[1]!r} / {b[1]!r}"
    assert a[1] == b[1], f"{label}: body differs\npython={json.dumps(a[1], indent=1)[:1500]}\nrust  ={json.dumps(b[1], indent=1)[:1500]}"
    for k in ("content-type", "cache-control", "x-content-type-options", "referrer-policy"):
        assert a[2].get(k) == b[2].get(k), f"{label}: header {k} python={a[2].get(k)} rust={b[2].get(k)}"
    n += 1
    print("PASS", label, a[0])
    return a


def main():
    procs = []
    try:
        # the Python API creates/updates the schema on start-up, exactly as in production
        procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PY)], cwd=ROOT / "api", env={**os.environ, **ENV},
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait(PY)
        procs.append(subprocess.Popen([str(BIN)], env={**os.environ, **ENV, "BIND": f"127.0.0.1:{RS}"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait(RS)

        psql("DELETE FROM tenants WHERE slug LIKE 'parity-%'")
        rows = [
            ("parity-open", "pk_parity_open", "Open Co", "{}", "true", "", "Friendly."),
            ("parity-closed", "pk_parity_closed", "Closed Co", '{"https://shop.example"}', "false", "Hello from Closed Co!", ""),
            ("parity-trailing", "pk_parity_trailing", "Ünï & Co", '{"https://a.example/","HTTP://B.EXAMPLE"}', "true", "", "p"),
            ("parity-nocal", "pk_parity_nocal", "No Calendar", "{}", "false", "", ""),
        ]
        for slug, key, name, origins, voice, greeting, persona in rows:
            psql(f"INSERT INTO tenants(slug,name,public_key,report_token,allowed_origins,voice_enabled,greeting,persona,site_url) VALUES('{slug}','{name}','{key}','rt_{slug}','{origins}',{voice},'{greeting}','{persona}','https://{slug}.example')")
        psql("UPDATE tenants SET calendar_token='ct_parity_open', scoring='{\"warm_at\": 20}'::jsonb, business_hours='{\"mon\": [[\"09:00\", \"17:00\"]]}'::jsonb WHERE slug='parity-open'")
        psql("INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) SELECT id,'call_recording',true,gen_random_uuid() FROM tenants WHERE slug IN ('parity-open')")
        psql("INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) SELECT id,'call_recording',false,gen_random_uuid() FROM tenants WHERE slug IN ('parity-trailing')")

        psql("INSERT INTO chunks(tenant_id,url,title,content,embedding) SELECT id,'manual:p'||g,'t','c',array_fill(0.1::real, ARRAY[384])::vector FROM tenants, generate_series(1,3) g WHERE slug='parity-open'")

        same("healthz", "/healthz")
        for key in ("pk_parity_open", "pk_parity_closed", "pk_parity_trailing", "pk_parity_nocal", "unknown", ""):
            same(f"widget-config {key!r}", f"/api/v1/widget-config?key={key}")
        same("widget-config missing key", "/api/v1/widget-config")
        for origin in ("https://shop.example", "https://SHOP.example/", "https://evil.example", "http://localhost:8000", ""):
            same(f"widget-config closed origin {origin!r}", "/api/v1/widget-config?key=pk_parity_closed", {"Origin": origin})
        for origin in ("https://a.example", "http://b.example", "https://c.example"):
            same(f"widget-config trailing origin {origin!r}", "/api/v1/widget-config?key=pk_parity_trailing", {"Origin": origin})
        same("cors header", "/api/v1/widget-config?key=pk_parity_open", {"Origin": "https://anything.example"})
        a = get(PY, "/api/v1/widget-config?key=pk_parity_open", {"Origin": "https://anything.example"})
        b = get(RS, "/api/v1/widget-config?key=pk_parity_open", {"Origin": "https://anything.example"})
        assert a[2].get("access-control-allow-origin") == b[2].get("access-control-allow-origin") == "*", (a[2], b[2])

        def only_ours(res):
            status, body, hdrs = res
            if isinstance(body, list):
                body = [t for t in body if str(t.get("slug", "")).startswith("parity-")]
            return status, body, hdrs

        same("admin list without token", "/admin/tenants")
        same("admin list wrong token", "/admin/tenants", {"X-Admin-Token": "nope"})
        same("admin list", "/admin/tenants", {"X-Admin-Token": "parity-admin"}, normalise=lambda r: _drop_times(only_ours(r)))
        for slug in ("parity-open", "parity-closed", "parity-nocal", "missing"):
            same(f"admin get {slug}", f"/admin/tenants/{slug}", {"X-Admin-Token": "parity-admin"}, normalise=lambda r: _drop_times(r))
        same("admin get without token", "/admin/tenants/parity-open")

        # ---------------------------------------------------------------- the client report
        # The report is the first token-in-path route. Its data is seeded below so both servers read the
        # same rows; the page is compared as exact text, which also proves the SVG bar arithmetic and the
        # html.escape rules. `report_token` was set at insert time above.
        psql("DELETE FROM conversations WHERE tenant_id IN (SELECT id FROM tenants WHERE slug LIKE 'parity-%')")
        psql("DELETE FROM outbox WHERE tenant_id IN (SELECT id FROM tenants WHERE slug LIKE 'parity-%')")
        # Two conversations on the open tenant: one chat, one eval (excluded), so by_channel and the totals differ.
        psql("INSERT INTO conversations(tenant_id,session_id,channel,started_at) SELECT id,'s1','chat',now() - interval '2 days' FROM tenants WHERE slug='parity-open'")
        psql("INSERT INTO conversations(tenant_id,session_id,channel,started_at) SELECT id,'s2','eval',now() - interval '2 days' FROM tenants WHERE slug='parity-open'")
        psql("INSERT INTO conversations(tenant_id,session_id,channel,started_at) SELECT id,'s3','sms',now() - interval '1 day' FROM tenants WHERE slug='parity-open'")
        # Leads with the awkward characters html.escape must handle, plus a long message and an empty name.
        psql("INSERT INTO leads(tenant_id,name,message,channel,status,score_label,created_at) SELECT id,'Ann & <b>Bob</b>','Wants a \"quote\" & <script>alert(1)</script> for it''s plan','chat','new','hot',now() - interval '2 days' FROM tenants WHERE slug='parity-open'")
        psql("INSERT INTO leads(tenant_id,name,message,channel,status,score_label,created_at) SELECT id,'','','sms','won','cold',now() - interval '1 day' FROM tenants WHERE slug='parity-open'")
        psql("INSERT INTO leads(tenant_id,name,message,channel,status,score_label,created_at) SELECT id,'Zoë Ñandú','é'||repeat('x',200),'voice','contacted','warm',now() - interval '3 days' FROM tenants WHERE slug='parity-open'")
        psql("INSERT INTO appointments(tenant_id,starts_at,ends_at,created_at) SELECT id,now() + interval '1 day',now() + interval '1 day 1 hour',now() - interval '1 day' FROM tenants WHERE slug='parity-open'")
        psql("UPDATE leads SET value_cents=2500, updated_at=now() - interval '1 day' WHERE tenant_id IN (SELECT id FROM tenants WHERE slug='parity-open') AND status='won'")
        # lead_value_cents drives "Estimated pipeline"; set it on one tenant and leave 0 on another to prove the "-" branch.
        psql("UPDATE tenants SET lead_value_cents=15000, accent_color='#ff00aa' WHERE slug='parity-open'")
        psql("UPDATE tenants SET lead_value_cents=0 WHERE slug='parity-closed'")

        same("report open", "/report/rt_parity-open")
        same("report closed (no data, no pipeline)", "/report/rt_parity-closed")
        same("report accented name", "/report/rt_parity-trailing")
        same("report unknown token", "/report/rt_nope")
        same("report empty token", "/report/")
        for days in ("1", "7", "30", "365", "366", "0", "-5", " 7 ", "+7"):
            same(f"report days={days!r}", f"/report/rt_parity-open?days={quote(days, safe='')}")
        for bad in ("abc", "1.5", "1e2", "0x10", ""):
            same(f"report bad days={bad!r}", f"/report/rt_parity-open?days={bad}")
        # The huge int is accepted by pydantic and clamped to 365, so it must compare equal to days=365.
        same("report days=10**24", "/report/rt_parity-open?days=1000000000000000000000000")

        # The empirical answer to "does the edge middleware compose onto a token-in-path route?":
        # a foreign Origin on /report/{token} must be served (not 403) and must NOT carry the owner-portal
        # hardening headers, because Python's owner_boundary only guards /owner-ui, /owner/* and
        # /api/v1/device-sms/*. Compare both servers, then assert the rule directly.
        for origin in ("https://evil.example", "http://127.0.0.1:8098", ""):
            same(f"report foreign origin {origin!r}", "/report/rt_parity-open", {"Origin": origin})
        a = get(PY, "/report/rt_parity-open", {"Origin": "https://evil.example"})
        b = get(RS, "/report/rt_parity-open", {"Origin": "https://evil.example"})
        assert a[0] == b[0] == 200, f"report must not be origin-gated: python={a[0]} rust={b[0]}"
        for h in ("cache-control", "x-content-type-options", "referrer-policy"):
            assert a[2].get(h) == b[2].get(h), f"report header {h} python={a[2].get(h)} rust={b[2].get(h)}"
        assert a[2].get("cache-control") is None, f"report must not be hardened, got {a[2].get('cache-control')}"
        print("ANSWER: /report/{token} is NOT behind the owner boundary (both servers, no hardening headers)")

        # ---------------------------------------------------------------- the calendar feed
        # `GET /api/v1/calendar/{token}.ics`. Starlette matches it with `(?P<token>[^/]+)\.ics$`, so the suffix
        # is required and the token must be non-empty; axum has no suffix syntax and captures the whole segment,
        # so these cases prove the handler reproduces Starlette's matching rather than axum's.
        psql("UPDATE tenants SET calendar_token='ct_parity-open' WHERE slug='parity-open'")
        psql("UPDATE tenants SET calendar_token='ct_parity_closed' WHERE slug='parity-closed'")
        # The token keeps its underscore: only the slug uses a hyphen. The two are deliberately spelled
        # differently here so a mismatch between them fails this comparison instead of passing as a 404.
        assert psql("SELECT calendar_token FROM tenants WHERE slug='parity-closed'") == "ct_parity_closed"
        # Appointments that exercise esc() and fold(): the calendar name and fields carry a comma, a semicolon,
        # a backslash and a newline, one appointment is cancelled, and one has no optional fields at all.
        psql("UPDATE tenants SET name='Open, Co; Ltd\\' WHERE slug='parity-open'")
        for lead_id, aid_off, starts, ends, status, name, phone, email, notes in [
            ("a1", 0, "-1 day", "-1 day", "booked", "Zoë Ñandú", "+64 21 555 0001", "zoe@example.com", "Line one\nLine two, with a comma; and a backslash \\\\ here"),
            ("a2", 1, "1 day", "1 day", "cancelled", "Bob, Jr.; \"Bobby\"", "", "", ""),
            ("a3", 2, "2 days", "2 days", "completed", "", "+64 21 555 0003", "", "semi;colon"),
            ("a4", 3, "40 days", "40 days", "booked", "Old Appointment", "+1", "o@e.com", "outside the 30-day window"),
        ]:
            psql(
                "INSERT INTO appointments(tenant_id,starts_at,ends_at,status,name,phone,email,notes) "
                f"SELECT id, now() + interval '{starts}', now() + interval '{ends}' + interval '1 hour', "
                f"'{status}', '{name}', '{phone}', '{email}', '{notes}' FROM tenants WHERE slug='parity-open'"
            )
        # A second tenant with no appointments at all: the empty feed.
        same("calendar feed with appointments", "/api/v1/calendar/ct_parity-open.ics", normalise=_drop_dtstamp)
        same("calendar feed empty", "/api/v1/calendar/ct_parity_closed.ics", normalise=_drop_dtstamp)
        # Starlette's matching, reproduced: the suffix is required and a one-character token is the minimum.
        same("calendar unknown token", "/api/v1/calendar/ct_nope.ics")
        same("calendar no suffix", "/api/v1/calendar/ct_parity-open")
        same("calendar suffix only", "/api/v1/calendar/.ics")
        same("calendar empty path", "/api/v1/calendar/")
        same("calendar token with a dot", "/api/v1/calendar/ct.parity.ics")
        same("calendar double suffix", "/api/v1/calendar/ct_parity-open.ics.ics")
        same("calendar nested path", "/api/v1/calendar/a/b.ics")
        same("calendar uppercase suffix", "/api/v1/calendar/ct_parity-open.ICS")
        # The feed is its own credential, so it is not origin-gated either, and it sets its own Cache-Control.
        for origin in ("https://evil.example", ""):
            same(f"calendar foreign origin {origin!r}", "/api/v1/calendar/ct_parity-open.ics",
                 {"Origin": origin}, normalise=_drop_dtstamp)
        c = get(PY, "/api/v1/calendar/ct_parity-open.ics")
        assert c[2].get("cache-control") == "private, max-age=300", c[2]
        assert c[2].get("content-type") == "text/calendar; charset=utf-8", c[2]

        # ---------------------------------------------------------------- the sandbox demo page
        # `GET /demo/{slug}` reads the tenant by slug and the FIRST chunk by id. Seeds:
        #  - parity-open: three chunks, demo questions with markup and an apostrophe;
        #  - parity-closed: two chunks, SECOND inserted first and FIRST inserted later with an explicit lower id, so heap
        #    position (which breaks ties inside chunks_tenant_idx) says SECOND while only `ORDER BY id` says FIRST. An
        #    earlier version rewrote the row with an UPDATE instead; that keeps its index position, so a mutant without
        #    ORDER BY survived it;
        #  - parity-trailing: a long non-ASCII excerpt with newlines and markup, hostile accent colour and site url, and
        #    demo_questions stored as a JSON *string* (so demo_page decodes it a second time);
        #  - parity-nocal: no chunks, a non-http site url, and demo_questions that is not JSON (a 500 even for presenter=0);
        #  - parity-dict: a JSON object, the one shape the port declines.
        psql("""UPDATE tenants SET demo_questions='["What are your hours?","Q & <b>x</b>","it''s"]'::jsonb WHERE slug='parity-open'""")
        psql("DELETE FROM chunks WHERE tenant_id IN (SELECT id FROM tenants WHERE slug IN ('parity-closed','parity-trailing'))")
        vec = "array_fill(0.1::real, ARRAY[384])::vector"
        psql(f"INSERT INTO chunks(tenant_id,url,title,content,embedding) SELECT id,'manual:second','t','SECOND chunk',{vec} FROM tenants WHERE slug='parity-closed'")
        psql(f"INSERT INTO chunks(id,tenant_id,url,title,content,embedding) SELECT -424242,id,'manual:first','t','FIRST chunk',{vec} FROM tenants WHERE slug='parity-closed'")
        assert psql("SELECT content FROM chunks WHERE tenant_id=(SELECT id FROM tenants WHERE slug='parity-closed') LIMIT 1") == "SECOND chunk", \
            "the seed must make an unordered read return SECOND, or the ORDER BY id mutant cannot be told apart"
        psql(f"INSERT INTO chunks(tenant_id,url,title,content,embedding) SELECT id,'manual:long','t','line1'||chr(10)||'<b>&</b> \"q\" it''s'||chr(13)||chr(10)||repeat('é',800),{vec} FROM tenants WHERE slug='parity-trailing'")
        psql(f"INSERT INTO chunks(tenant_id,url,title,content,embedding) SELECT id,'manual:later','t','later chunk',{vec} FROM tenants WHERE slug='parity-trailing'")
        psql("""UPDATE tenants SET demo_questions='"[\\"a\\",\\"b & <c>\\"]"'::jsonb, accent_color='"><x>&', site_url='https://<b>&"x' WHERE slug='parity-trailing'""")
        psql("""UPDATE tenants SET demo_questions='"not json"'::jsonb, site_url='ftp://nope.example' WHERE slug='parity-nocal'""")
        psql("""INSERT INTO tenants(slug,name,public_key,report_token,demo_questions) VALUES('parity-dict','Dict Co','pk_parity_dict','rt_parity-dict','{"k": 1, "b": 2}'::jsonb)""")
        for slug in ("parity-open", "parity-closed", "parity-trailing"):
            for presenter in ("", "?presenter=0", "?presenter=1", "?presenter=2", "?presenter=-1"):
                same(f"demo {slug}{presenter}", f"/demo/{slug}{presenter}")
        same("demo no chunks and non-http site", "/demo/parity-nocal?presenter=0&x=1")
        same("demo undecodable questions (500 even for presenter=0)", "/demo/parity-nocal")
        same("demo undecodable questions with presenter", "/demo/parity-nocal?presenter=1")
        assert get(PY, "/demo/parity-nocal")[0] == get(RS, "/demo/parity-nocal")[0] == 500
        same("demo dict questions, presenter=0", "/demo/parity-dict")
        py_dict, rs_dict = get(PY, "/demo/parity-dict?presenter=1"), get(RS, "/demo/parity-dict?presenter=1")
        assert py_dict[0] == 200 and "<li>k</li>" in py_dict[1], py_dict
        assert rs_dict[0] == 500, "the declined shape must fail closed, not guess jsonb key order"
        print("ANSWER: a JSON-object demo_questions is declined (Rust 500, Python renders the keys), as documented")
        for raw in ("1", " 1 ", "+1", "01", "1_0", "true", "abc", "1.5", "1e2", "0x10", "", "٣", "1000000000000000000000000"):
            same(f"demo presenter={raw!r}", f"/demo/parity-open?presenter={quote(raw, safe='')}")
        same("demo repeated presenter (last wins)", "/demo/parity-open?presenter=0&presenter=1")
        same("demo unknown slug", "/demo/missing")
        same("demo unknown slug, bad presenter (422 beats 404)", "/demo/missing?presenter=abc")
        same("demo empty slug", "/demo/")
        same("demo nested path", "/demo/parity-open/extra")
        same("demo slug is case-sensitive", "/demo/PARITY-OPEN")
        same("demo percent-encoded slug", "/demo/parity%2Dopen?presenter=1")
        same("demo encoded slash in slug", "/demo/parity%2Fopen")
        same("demo slug with a space", "/demo/parity%20open")
        for origin in ("https://evil.example", ""):
            same(f"demo foreign origin {origin!r}", "/demo/parity-open?presenter=1", {"Origin": origin})
        d = get(RS, "/demo/parity-open?presenter=1", {"Origin": "https://evil.example"})
        assert d[0] == 200 and d[2].get("cache-control") is None, d[2]
        assert d[2].get("content-type") == "text/html; charset=utf-8", d[2]

        # ---------------------------------------------------------------- encoded slash in a path segment
        # Starlette routes on the DECODED path, so `%2F` is a `/` that `[^/]+` cannot match: the router's plain
        # "Not Found", decided before the admin gate or any query validation. axum routes on the raw path.
        admin = {"X-Admin-Token": "parity-admin"}
        same("report encoded slash", "/report/rt_parity-open%2Fx")
        same("report encoded slash, bad days (404 beats 422)", "/report/rt_parity-open%2Fx?days=abc")
        same("calendar encoded slash", "/api/v1/calendar/ct%2Fx.ics")
        same("calendar encoded slash before suffix", "/api/v1/calendar/ct_parity-open%2F.ics")
        same("admin encoded slash", "/admin/tenants/parity%2Fopen", admin)
        same("admin encoded slash without token (404 beats 401)", "/admin/tenants/parity%2Fopen")
        same("report encoded dash still routes", "/report/rt_parity%2Dopen")

        print(f"{n} comparisons passed")
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        psql("DELETE FROM tenants WHERE slug LIKE 'parity-%'")


def _drop_dtstamp(res):
    """`DTSTAMP` is the moment each server built the feed, so it legitimately differs by up to a second: replace
    it with a placeholder and keep every other byte, which is where esc() and fold() show up."""
    status, body, hdrs = res
    if isinstance(body, str) and "DTSTAMP:" in body:
        body = re.sub(r"DTSTAMP:\d{8}T\d{6}Z", "DTSTAMP:<now>", body)
    return status, body, hdrs


def _drop_times(res):
    """created_at differs only by insertion time of the shared rows: it is the same row for both servers, so keep it. Tokens minted on first read are random."""
    status, body, hdrs = res
    if isinstance(body, dict) and body.get("slug") == "parity-nocal":
        body = {k: ("<minted>" if k in ("calendar_token", "calendar_url") else v) for k, v in body.items()}
        body["calendar_url"] = "<minted>" if body.get("calendar_url") else body.get("calendar_url")
    return status, body, hdrs


if __name__ == "__main__":
    main()
