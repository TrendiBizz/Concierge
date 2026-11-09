"""Differential test: the real Rust server (concierge-server) and the real Python API answer the SAME requests over the SAME PostgreSQL.

Local run (needs Postgres at 127.0.0.1:55432 with the API schema applied by the API itself, a built binary and the API's Python deps):

    cargo build --release --manifest-path concierge-stack/server-rs/Cargo.toml
    PYTHONPATH=QA/verification/shims:api python QA/verification/rust_server_parity.py

Starts two loopback servers, sends nothing anywhere, and removes the rows it creates. Compares status, JSON body, content type and the security headers.
"""
import base64
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
ALT_PY, ALT_RS = PY + 2, RS + 2  # a second and third pair of servers with different settings (see `start_alt_pair`)
SIP_PY, SIP_RS = PY + 4, RS + 4
ENV = {"DATABASE_URL": DB, "ADMIN_TOKEN": "parity-admin", "PUBLIC_BASE_URL": "http://localhost:8000", "VOICE_RECORDING_ENABLED": "true", "OUTBOX_ENABLED": "false", "UNSUBSCRIBE_SECRET": "parity-unsub-secret",
       # settings read by the owner-portal overview, readiness report and email-draft gate (main pair: draft workflow on, telephone NOT ready
       # because PUBLIC_BASE_URL is not https; the alternate pairs below flip those)
       "EMAIL_DRAFTS_ENABLED": "true", "LLM_API_KEY": "parity-llm", "WEBSITE_VERIFIED_TENANTS": "parity-open , parity-closed", "PHONE_VERIFIED_TENANTS": "parity-open",
       "PHONE_RECEPTIONIST_ENABLED": "true", "PHONE_VOICE_PROVIDER": "legacy_twilio_tts", "TWILIO_ACCOUNT_SID": "ACparity", "TWILIO_AUTH_TOKEN": "parity-token",
       "TWILIO_FROM_NUMBER": "+15550001111", "SMS_PROVIDER": "twilio", "SMTP_HOST": "smtp.parity.invalid", "SMTP_FROM": "from@parity.invalid",
       "PHONE_RECORDING_ENABLED": "true", "INBOUND_CLOUDFLARE_ENABLED": "true"}
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


def get_raw(port, path, headers=None):
    """Like `get` but binary-safe and with every response header, for audio and cookie-free token routes."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}


RAW_KEYS = ("content-type", "cache-control", "x-content-type-options", "referrer-policy", "x-robots-tag", "content-disposition", "content-length",
            "access-control-allow-origin")


def same_raw(label, path, headers=None, ports=None):
    """Byte-exact body and the full set of response headers that matter, for binary and HTML routes. `ports` selects
    the alternate server pair (different settings) instead of the main one."""
    global n
    py, rs = ports or (PY, RS)
    a, b = get_raw(py, path, headers), get_raw(rs, path, headers)
    assert a[0] == b[0], f"{label}: status python={a[0]} rust={b[0]} body={a[1][:200]!r} / {b[1][:200]!r}"
    assert a[1] == b[1], f"{label}: body differs\npython={a[1][:600]!r}\nrust  ={b[1][:600]!r}"
    for k in RAW_KEYS:
        # Rust's CorsLayer answers `access-control-allow-origin: *` even without an Origin header, Python's middleware only with one
        # (a pre-existing difference of the shared CORS layer, recorded in PORT_STATUS): compare it only when the request sent an Origin.
        # The owner boundary's 403 is answered before Python's CORS middleware (no header), while Rust's CorsLayer wraps it (`*`): a
        # second pre-existing difference, skipped for refusals.
        if k == "access-control-allow-origin" and (not (headers or {}).get("Origin") or a[0] == 403):
            continue
        assert a[2].get(k) == b[2].get(k), f"{label}: header {k} python={a[2].get(k)} rust={b[2].get(k)}"
    n += 1
    print("PASS", label, a[0])
    return a


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


def start_alt_pair(procs, env_over, py_port=None, rs_port=None):
    """A second Python + Rust pair on the same database whose settings differ from the main pair's, for rules that depend on
    configuration (a disabled feature, an unset secret)."""
    py_port, rs_port = py_port or ALT_PY, rs_port or ALT_RS
    env = {**os.environ, **ENV, **env_over}
    procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(py_port)], cwd=ROOT / "api", env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    wait(py_port)
    procs.append(subprocess.Popen([str(BIN)], env={**env, "BIND": f"127.0.0.1:{rs_port}"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    wait(rs_port)


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


        # ---------------------------------------------------------------- batch 40, family 1: public token-in-path reads
        import hashlib
        from app import unsub as py_unsub

        py_unsub._secret = lambda: b"parity-unsub-secret"  # both servers run with UNSUBSCRIBE_SECRET set, which wins over ADMIN_TOKEN

        def unsub_token(payload):
            return payload + "." + py_unsub._sign(payload)

        good_unsub = py_unsub.make_token("11111111-1111-1111-1111-111111111111", "a@b.co")
        gp, gsig = good_unsub.split(".")
        for label, tok in [
            ("valid", good_unsub), ("unknown", "nope"), ("bad signature", gp + ".0" * 1), ("signature one char off", gp + "." + gsig[:-1] + ("0" if gsig[-1] != "0" else "1")),
            ("no signature", gp), ("empty signature", gp + "."), ("empty payload", "." + gsig), ("only a dot", "."), ("trailing junk", good_unsub + "x"),
            ("padded payload", unsub_token(base64.urlsafe_b64encode(b"t|c").decode())), ("unpadded payload", unsub_token("dHxj")),
            ("payload with stray bang", unsub_token("dHxj!")), ("payload with space", unsub_token("dH xj")),
            ("payload not utf-8", unsub_token(base64.urlsafe_b64encode(b"\xff\xfe|x").decode())),
            ("payload without pipe", unsub_token(base64.urlsafe_b64encode(b"tenantonly").decode())),
            ("payload with empty contact", unsub_token(base64.urlsafe_b64encode(b"t|").decode())),
            ("payload non-ascii", unsub_token("é")), ("non-ascii signature (Python raises, 500)", gp + ".é"),
            ("percent-encoded dot", gp + "%2E" + gsig), ("html in token", "<b>&"),
        ]:
            same_raw(f"unsubscribe {label}", f"/api/v1/unsubscribe/{quote(tok, safe='.-_=')}")
        # A token signed with the ADMIN_TOKEN fallback must NOT verify while UNSUBSCRIBE_SECRET is set.
        py_unsub._secret = lambda: b"parity-admin"
        admin_signed = py_unsub.make_token("11111111-1111-1111-1111-111111111111", "a@b.co")
        py_unsub._secret = lambda: b"parity-unsub-secret"
        same_raw("unsubscribe token signed with the fallback secret is refused", f"/api/v1/unsubscribe/{admin_signed}")
        assert get_raw(PY, f"/api/v1/unsubscribe/{admin_signed}")[0] == 404 and get_raw(PY, f"/api/v1/unsubscribe/{good_unsub}")[0] == 200
        # The alternate pair has no UNSUBSCRIBE_SECRET: the signing secret falls back to ADMIN_TOKEN ("parity-admin").
        start_alt_pair(procs, {"UNSUBSCRIBE_SECRET": "", "EMAIL_DRAFTS_ENABLED": "false", "PUBLIC_BASE_URL": "https://parity.example", "SMS_PROVIDER": "smsgate",
                               "SMSGATE_BASE_URL": "https://sms.invalid", "SMSGATE_USERNAME": "u", "SMSGATE_PASSWORD": "p", "PHONE_VOICE_PROVIDER": "legacy_twilio_tts"})
        alt = (ALT_PY, ALT_RS)
        same_raw("unsubscribe (fallback secret) token signed with ADMIN_TOKEN", f"/api/v1/unsubscribe/{admin_signed}", ports=alt)
        same_raw("unsubscribe (fallback secret) token signed with UNSUBSCRIBE_SECRET is refused", f"/api/v1/unsubscribe/{good_unsub}", ports=alt)
        assert get_raw(ALT_PY, f"/api/v1/unsubscribe/{admin_signed}")[0] == 200 and get_raw(ALT_PY, f"/api/v1/unsubscribe/{good_unsub}")[0] == 404
        same_raw("unsubscribe empty token", "/api/v1/unsubscribe/")
        same_raw("unsubscribe nested path", f"/api/v1/unsubscribe/{good_unsub}/x")
        same_raw("unsubscribe encoded slash", f"/api/v1/unsubscribe/{gp}%2F{gsig}")
        same_raw("unsubscribe invalid utf-8 percent escape", "/api/v1/unsubscribe/%ff")
        same_raw("unsubscribe foreign origin is not gated", f"/api/v1/unsubscribe/{good_unsub}", {"Origin": "https://evil.example"})
        same_raw("unsubscribe query string ignored", f"/api/v1/unsubscribe/{good_unsub}?x=1")
        assert get_raw(PY, f"/api/v1/unsubscribe/{good_unsub}")[0] == 200 and get_raw(PY, f"/api/v1/unsubscribe/{gp}.%C3%A9")[0] == 500

        # Shared voice recordings: the link is its own credential. Seeds cover every mime type, an expired share, a recording
        # older than 30 days, a share whose tenant does not match its recording, and the length limits (32..=100 characters).
        psql("DELETE FROM conversations WHERE tenant_id IN (SELECT id FROM tenants WHERE slug LIKE 'parity-%')")
        every_byte = bytes(range(256)).hex()
        sha = lambda t: hashlib.sha256(t.encode()).hexdigest()  # noqa: E731
        shares = {}  # label -> token
        for label, mime, token, share_age, rec_age in [
            ("webm", "audio/webm", "w" * 43, "+ interval '1 hour'", "now()"), ("ogg", "audio/ogg", "o" * 32, "+ interval '1 hour'", "now()"), ("mp4", "audio/mp4", "m" * 100, "+ interval '1 hour'", "now()"),
            ("wav", "audio/wav", "v" * 50, "+ interval '1 hour'", "now()"), ("expired", "audio/webm", "e" * 43, "- interval '1 minute'", "now()"),
            ("stale", "audio/webm", "s" * 43, "+ interval '1 hour'", "now() - interval '31 days'"), ("fresh29", "audio/webm", "f" * 43, "+ interval '1 hour'", "now() - interval '29 days'"),
            # Stored shares at the length limits: only the length rule can refuse these (an unknown token of the same length answers the same 404).
            ("len31", "audio/webm", "t" * 31, "+ interval '1 hour'", "now()"), ("len101", "audio/webm", "l" * 101, "+ interval '1 hour'", "now()"),
            ("chars20-bytes40", "audio/ogg", "é" * 20, "+ interval '1 hour'", "now()"), ("chars51-bytes102", "audio/ogg", "é" * 51, "+ interval '1 hour'", "now()"),
        ]:
            shares[label] = token
            psql(f"INSERT INTO conversations(tenant_id,session_id,channel) SELECT id,'rec-{label}','voice' FROM tenants WHERE slug='parity-open'")
            psql(f"INSERT INTO voice_sessions(id,tenant_id,conversation_id,token_hash) SELECT ('00000000-0000-4000-8000-0000000000'||lpad('{len(shares)}',2,'0'))::uuid,t.id,c.id,'vs-{label}' "
                 f"FROM tenants t JOIN conversations c ON c.tenant_id=t.id AND c.session_id='rec-{label}' WHERE t.slug='parity-open'")
            psql(f"INSERT INTO voice_recordings(session_id,tenant_id,conversation_id,mime_type,audio,sha256,created_at) "
                 f"SELECT s.id,s.tenant_id,s.conversation_id,'{mime}',decode('{every_byte}','hex'),'x',{rec_age} FROM voice_sessions s WHERE s.token_hash='vs-{label}'")
            psql(f"INSERT INTO voice_recording_shares(token_hash,session_id,tenant_id,expires_at) SELECT '{sha(token)}',s.id,s.tenant_id,now() {share_age} "
                 f"FROM voice_sessions s WHERE s.token_hash='vs-{label}'")
        # A share that points at the right session but names ANOTHER tenant must not play: the join requires both ids to match.
        psql("INSERT INTO voice_recording_shares(token_hash,session_id,tenant_id) SELECT '" + sha("x" * 43) + "',s.id,(SELECT id FROM tenants WHERE slug='parity-closed') FROM voice_sessions s WHERE s.token_hash='vs-webm'")
        for label, token in shares.items():
            same_raw(f"shared recording {label}", "/api/v1/voice/recordings/shared/" + quote(token))
        same_raw("shared recording share names another tenant", "/api/v1/voice/recordings/shared/" + "x" * 43)
        same_raw("shared recording unknown token", "/api/v1/voice/recordings/shared/" + "u" * 43)
        for length in (0, 1, 31, 101, 500):
            same_raw(f"shared recording token length {length}", "/api/v1/voice/recordings/shared/" + "w" * length)
        same_raw("shared recording token of 32 non-ascii characters", "/api/v1/voice/recordings/shared/" + quote("é" * 32))
        same_raw("shared recording 31 non-ascii characters (byte length would pass)", "/api/v1/voice/recordings/shared/" + quote("é" * 31))
        same_raw("shared recording token with a space", "/api/v1/voice/recordings/shared/" + quote("w" * 20 + " " + "w" * 20))
        same_raw("shared recording encoded slash", "/api/v1/voice/recordings/shared/" + "w" * 20 + "%2F" + "w" * 20)
        same_raw("shared recording nested path", "/api/v1/voice/recordings/shared/" + "w" * 43 + "/x")
        same_raw("shared recording foreign origin is not gated", "/api/v1/voice/recordings/shared/" + "w" * 43, {"Origin": "https://evil.example"})
        a = get_raw(RS, "/api/v1/voice/recordings/shared/" + "w" * 43)
        assert a[0] == 200 and a[1] == bytes(range(256)) and a[2]["cache-control"] == "private, no-store", a[2]
        assert a[2]["content-disposition"] == 'inline; filename="concierge-recording.webm"', a[2]

        # Social media proxy. The harness runs with the social service OFF, so both servers answer from `_configuration()`;
        # the proxying itself (an outbound request) is not ported, see PORT_STATUS.
        for label, tok in [("token", "abc"), ("2048 chars", "a" * 2048), ("2049 chars (404 before the 503)", "a" * 2049), ("2049 non-ascii chars", "é" * 2049),
                           ("2048 non-ascii chars", "é" * 2048)]:
            same_raw(f"social-media {label}", "/api/v1/social-media/" + quote(tok))
        same_raw("social-media empty token", "/api/v1/social-media/")
        same_raw("social-media encoded slash", "/api/v1/social-media/a%2Fb")
        same_raw("social-media nested", "/api/v1/social-media/a/b")


        # ---------------------------------------------------------------- batch 40, family 2: owner-portal reads
        # Every route authenticates with `Authorization: Bearer <token>` (owner_auth.current_user: SHA-256 of the token looked
        # up in tenant_sessions, unexpired, user active). The first token comes from the REAL Python POST /owner/auth/login
        # (a real pbkdf2 hash), the others are inserted exactly as login inserts them. Isolation is tested with a second
        # tenant that has rows of every kind.
        import http.client
        global n
        from app import owner_auth as py_owner

        def owner_user(slug, email, role, active=True, password_hash="x"):
            psql(f"INSERT INTO tenant_users(tenant_id,email,role,password_hash,active) SELECT id,'{email}','{role}','{password_hash}',{str(active).lower()} FROM tenants WHERE slug='{slug}'")

        def owner_session(email, token, expires="+ interval '1 hour'"):
            psql(f"INSERT INTO tenant_sessions(user_id,token_hash,expires_at) SELECT id,'{py_owner.digest(token)}',now() {expires} FROM tenant_users WHERE email='{email}'")

        psql("DELETE FROM tenant_users WHERE email LIKE '%@parity.invalid'")
        psql("DELETE FROM owner_login_limits")
        owner_user("parity-open", "owner@parity.invalid", "owner", password_hash=py_owner.password_hash("parity-password-1"))
        owner_user("parity-open", "viewer@parity.invalid", "viewer")
        owner_user("parity-open", "gone@parity.invalid", "owner", active=False)
        owner_user("parity-closed", "owner-b@parity.invalid", "owner")
        owner_user("parity-trailing", "owner-c@parity.invalid", "editor")
        login = json.dumps({"slug": "parity-open", "email": "owner@parity.invalid", "password": "parity-password-1"}).encode()
        rq = urllib.request.Request(f"http://127.0.0.1:{PY}/owner/auth/login", data=login, headers={"Content-Type": "application/json"})
        tok_a = json.load(urllib.request.urlopen(rq, timeout=30))["access_token"]  # the real login
        tok_viewer, tok_b, tok_c, tok_gone, tok_expired = "tv" + "v" * 40, "tb" + "b" * 40, "tc" + "c" * 40, "tg" + "g" * 40, "te" + "e" * 40
        owner_session("viewer@parity.invalid", tok_viewer)
        owner_session("owner-b@parity.invalid", tok_b)
        owner_session("owner-c@parity.invalid", tok_c)
        owner_session("gone@parity.invalid", tok_gone)
        owner_session("owner@parity.invalid", tok_expired, "- interval '1 second'")

        # ---- seeds. Tenant A = parity-open (rich), B = parity-closed (rich, different values), C = parity-trailing (empty).
        for slug in ("parity-open", "parity-closed"):
            psql(f"DELETE FROM leads WHERE tenant_id=(SELECT id FROM tenants WHERE slug='{slug}')")
        psql("DELETE FROM tasks WHERE tenant_id IN (SELECT id FROM tenants WHERE slug LIKE 'parity-%')")

        def conversation(slug, session, channel, msgs):
            psql(f"INSERT INTO conversations(tenant_id,session_id,channel) SELECT id,'{session}','{channel}' FROM tenants WHERE slug='{slug}'")
            for i, (role, content) in enumerate(msgs):
                psql(f"INSERT INTO messages(conversation_id,role,content,created_at) SELECT c.id,'{role}','{content}',now() - interval '{100 - i} minutes' "
                     f"FROM conversations c JOIN tenants t ON t.id=c.tenant_id WHERE t.slug='{slug}' AND c.session_id='{session}' AND c.channel='{channel}'")

        def lead(slug, key, name, convo=None, src=None, age="1 hour", utm="{}", status="new", score=0):
            conv = f"(SELECT c.id FROM conversations c JOIN tenants t ON t.id=c.tenant_id WHERE t.slug='{slug}' AND c.session_id='{convo}')" if convo else "NULL"
            psql(f"INSERT INTO leads(id,tenant_id,conversation_id,name,email,phone,message,channel,utm,created_at,status,score,score_label,score_reasons,notes) "
                 f"SELECT '{key}',id,{conv},'{name}','e@x.invalid','+6421{key[:4].replace('-', '0')[:3]}','msg {name}','chat','{utm}'::jsonb,now() - interval '{age}','{status}',{score},"
                 f"'warm','[\"asked price\", \"é\"]'::jsonb,'notes <b>&' FROM tenants WHERE slug='{slug}'")
            for j, text in enumerate(src or []):
                psql(f"INSERT INTO enquiry_sources(tenant_id,channel,source_key,lead_id,original_text,created_at) SELECT id,'email','{key}-{j}','{key}','{text}',now() - interval '{age}' + interval '{j} minutes' "
                     f"FROM tenants WHERE slug='{slug}'")

        conversation("parity-open", "ct1", "chat", [("system", "hidden prompt"), ("user", "Hi <b>there</b> &amp; it''s \"me\" é中"), ("assistant", "Hello!"), ("tool", "tool out"), ("user", "line1\nline2")])
        conversation("parity-open", "ct2", "chat", [("system", "only a system message")])
        conversation("parity-closed", "ctB", "chat", [("user", "B SECRET message"), ("assistant", "B reply")])
        LA1, LA2, LA3, LA4, LB1 = ("aaaaaaa1-0000-4000-8000-000000000001", "aaaaaaa2-0000-4000-8000-000000000002", "aaaaaaa3-0000-4000-8000-000000000003",
                                   "aaaaaaa4-0000-4000-8000-000000000004", "bbbbbbb1-0000-4000-8000-000000000001")
        lead("parity-open", LA1, "Ann <b>&", convo="ct1", age="3 hours", utm='{"src": "é", "n": 1}', status="won", score=70)
        lead("parity-open", LA2, "Bob", convo="ct2", src=["first original <i>text</i>", "second é original"], age="2 hours")
        lead("parity-open", LA3, "Cy no source", age="90 minutes", score=5)
        lead("parity-open", LA4, "Di sources only", src=["only source"], age="80 minutes")
        lead("parity-closed", LB1, "Bea B", convo="ctB", src=["B original"], age="1 hour", score=99)
        psql("UPDATE leads SET next_action_at=now() + interval '1 day', won_at=now() WHERE id='" + LA1 + "'")
        # tasks (A has a lead-linked open task, a done one, and one without a lead; B has one)
        psql("INSERT INTO tasks(tenant_id,lead_id,title,notes,due_at,status,kind,source,created_at,completed_at) SELECT id,'" + LA1 + "','Call Ann <b>','n \"q\"',now() + interval '1 day','open','follow_up','auto',now() - interval '5 hours',NULL FROM tenants WHERE slug='parity-open'")
        psql("INSERT INTO tasks(tenant_id,lead_id,title,status,kind,created_at,completed_at) SELECT id,NULL,'Done thing','done','manual',now() - interval '9 hours',now() - interval '1 hour' FROM tenants WHERE slug='parity-open'")
        psql("INSERT INTO tasks(tenant_id,lead_id,title,created_at) SELECT id,NULL,'B task',now() - interval '4 hours' FROM tenants WHERE slug='parity-closed'")
        # a voice recording tied to lead A1's conversation (and one tied to B's, so a missing tenant filter shows)
        psql("INSERT INTO voice_sessions(id,tenant_id,conversation_id,token_hash) SELECT '00000000-0000-4000-8000-0000000000a1',c.tenant_id,c.id,'vs-lead-a' FROM conversations c JOIN tenants t ON t.id=c.tenant_id WHERE t.slug='parity-open' AND c.session_id='ct1'")
        psql("INSERT INTO voice_recordings(session_id,tenant_id,conversation_id,mime_type,audio,sha256,created_at) SELECT id,tenant_id,conversation_id,'audio/webm',decode('0102030405','hex'),'x',now() - interval '2 days' FROM voice_sessions WHERE token_hash='vs-lead-a'")
        psql("INSERT INTO voice_sessions(id,tenant_id,conversation_id,token_hash) SELECT '00000000-0000-4000-8000-0000000000a2',c.tenant_id,c.id,'vs-lead-a-old' FROM conversations c JOIN tenants t ON t.id=c.tenant_id WHERE t.slug='parity-open' AND c.session_id='ct1'")
        psql("INSERT INTO voice_recordings(session_id,tenant_id,conversation_id,mime_type,audio,sha256,created_at) SELECT id,tenant_id,conversation_id,'audio/ogg',decode('0102','hex'),'x',now() - interval '40 days' FROM voice_sessions WHERE token_hash='vs-lead-a-old'")
        psql("INSERT INTO voice_sessions(id,tenant_id,conversation_id,token_hash) SELECT '00000000-0000-4000-8000-0000000000b1',c.tenant_id,c.id,'vs-lead-b' FROM conversations c JOIN tenants t ON t.id=c.tenant_id WHERE t.slug='parity-closed' AND c.session_id='ctB'")
        psql("INSERT INTO voice_recordings(session_id,tenant_id,conversation_id,mime_type,audio,sha256,created_at) SELECT id,tenant_id,conversation_id,'audio/mp4',decode('0102030405060708','hex'),'x',now() - interval '1 day' FROM voice_sessions WHERE token_hash='vs-lead-b'")
        # phone: numbers, setup, calls (with transcripts on phone-channel conversations only)
        psql("DELETE FROM phone_numbers WHERE tenant_id IN (SELECT id FROM tenants WHERE slug LIKE 'parity-%')")
        psql("INSERT INTO phone_numbers(e164,tenant_id,enabled,created_at) SELECT '+6499000001',id,true,now() - interval '3 days' FROM tenants WHERE slug='parity-open'")
        psql("INSERT INTO phone_numbers(e164,tenant_id,enabled,created_at) SELECT '+6499000002',id,false,now() - interval '2 days' FROM tenants WHERE slug='parity-open'")
        psql("INSERT INTO phone_numbers(e164,tenant_id,enabled) SELECT '+6499000003',id,true FROM tenants WHERE slug='parity-closed'")
        psql("INSERT INTO managed_phone_setups(tenant_id,designated_number,connection,answer_mode,owner_number,status) SELECT id,'+6499000001','existing_sip','unanswered','+64211234567','test_required' FROM tenants WHERE slug='parity-open' ON CONFLICT (tenant_id) DO NOTHING")
        psql("INSERT INTO managed_phone_setups(tenant_id,designated_number,connection,answer_mode,owner_number) SELECT id,'+6499000003','mobile_forwarding','all_calls','+64210000000' FROM tenants WHERE slug='parity-closed' ON CONFLICT (tenant_id) DO NOTHING")
        psql("DELETE FROM phone_calls WHERE tenant_id IN (SELECT id FROM tenants WHERE slug LIKE 'parity-%')")
        for sid, slug, frm, status, started, ended in [("CA-a1", "parity-open", "+64211111111", "completed", "2 hours", "now() - interval '1 hour'"), ("CA-a2", "parity-open", "", "ringing", "1 hour", "NULL"),
                                                       ("CA a/3 é", "parity-open", "+64212222222", "completed", "30 minutes", "now()"), ("CA-b1", "parity-closed", "+6421999", "completed", "10 minutes", "now()")]:
            psql(f"INSERT INTO phone_calls(call_sid,tenant_id,from_number,to_number,status,started_at,ended_at,recording_consent,recording_status) "
                 f"SELECT '{sid}',id,'{frm}','+6499000001','{status}',now() - interval '{started}',{ended},'granted','not_started' FROM tenants WHERE slug='{slug}'")
        conversation("parity-open", "CA-a1", "phone", [("system", "s"), ("user", "Hello caller <b>&"), ("assistant", "Hi, how can I help?"), ("tool", "x"), ("user", "é中")])
        conversation("parity-open", "CA-a1", "chat", [("user", "NOT a phone message")])
        conversation("parity-closed", "CA-b1", "phone", [("user", "B call secret")])
        # channel authorizations (one authorized, one revoked; the rest absent) and knowledge documents
        psql("DELETE FROM tenant_channel_authorizations WHERE tenant_id IN (SELECT id FROM tenants WHERE slug LIKE 'parity-%')")
        psql("INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id,updated_at) SELECT id,'telephone',true,gen_random_uuid(),'2026-11-01 10:00:00.123456+00' FROM tenants WHERE slug='parity-open'")
        psql("INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id,updated_at) SELECT id,'social',false,gen_random_uuid(),'2026-11-02 00:00:00+00' FROM tenants WHERE slug='parity-open'")
        psql("INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) SELECT id,'sms_send',true,gen_random_uuid() FROM tenants WHERE slug='parity-closed'")
        psql("DELETE FROM chunks WHERE tenant_id IN (SELECT id FROM tenants WHERE slug IN ('parity-open','parity-closed','parity-trailing')) AND url LIKE 'manual:owner:%'")
        vec = "array_fill(0.1::real, ARRAY[384])::vector"
        for slug, url, title, count in [("parity-open", "manual:owner:abc123", "Zebra <doc> & é", 3), ("parity-open", "manual:owner:def456", "Apple doc", 1),
                                        ("parity-open", "manual:owner:", "Empty id doc", 1), ("parity-closed", "manual:owner:bbb999", "B only doc", 2)]:
            psql(f"INSERT INTO chunks(tenant_id,url,title,content,embedding) SELECT id,'{url}','{title}','c',{vec} FROM tenants, generate_series(1,{count}) WHERE slug='{slug}'")
        psql(f"INSERT INTO chunks(tenant_id,url,title,content,embedding) SELECT id,'manual:owner:untitled','','c',{vec} FROM tenants WHERE slug='parity-open'")
        # email drafts
        psql("DELETE FROM email_drafts WHERE tenant_id IN (SELECT id FROM tenants WHERE slug LIKE 'parity-%')")
        for slug, status, subject, body in [("parity-open", "draft", "Hello <b>", "Reply & more"), ("parity-open", "draft", "", "Second"), ("parity-open", "approved", "Approved", "ok"),
                                            ("parity-open", "discarded", "Gone é", "bye"), ("parity-closed", "draft", "B draft", "B reply")]:
            psql(f"INSERT INTO email_drafts(tenant_id,sender,subject,inbound_body,reply_body,status) SELECT id,'a@x.invalid','{subject}','inbound','{body}','{status}' FROM tenants WHERE slug='{slug}'")
        # overview inputs: A has a paired, online, fully verified phone and telephone on; B has nothing configured
        psql("UPDATE tenants SET phone_enabled=true, sms_enabled=true, sms_transport='device', notify_email='boss@x.invalid', notify_phone='+64211234567', email_auto_reply=true, native_booking=true, slot_minutes=45, timezone='Pacific/Auckland' WHERE slug='parity-open'")
        psql("DELETE FROM sms_devices WHERE tenant_id IN (SELECT id FROM tenants WHERE slug LIKE 'parity-%')")
        psql("INSERT INTO sms_devices(tenant_id,token_hash,from_number,enabled,last_seen,verified_at,inbound_verified_at) SELECT id,'dev-parity-open','+6421000',true,now() - interval '10 seconds',now(),now() FROM tenants WHERE slug='parity-open'")
        psql("UPDATE tenants SET phone_enabled=true, sms_enabled=true, sms_transport='', notify_email='', site_url='' , voice_enabled=true WHERE slug='parity-closed'")
        psql("UPDATE tenants SET calendar_token='ct_parity_open' WHERE slug='parity-open'")
        psql("UPDATE tenants SET calendar_token='ct_parity_closed' WHERE slug='parity-closed'")

        def bearer(token):
            return {"Authorization": f"Bearer {token}"}

        # ---- authentication matrix, on EVERY route (the 401 decisions come before any path or query validation)
        OWNER_ROUTES = ["/owner/me", "/owner/crm", f"/owner/crm/leads/{LA1}/transcript", f"/owner/crm/leads/{LA1}/recordings", "/owner/onboarding",
                        "/owner/onboarding/authorizations", "/owner/onboarding/readiness", "/owner/knowledge", "/owner/email-drafts", "/owner/phone-setup",
                        "/owner/phone-numbers", "/owner/phone-calls", "/owner/phone-calls/CA-a1/transcript"]
        auth_cases = [
            ("no header", None), ("empty header", {"Authorization": ""}), ("scheme only", {"Authorization": "Bearer"}), ("scheme and empty token", {"Authorization": "Bearer "}),
            ("lower-case scheme", {"Authorization": "bearer " + tok_a}), ("upper-case scheme", {"Authorization": "BEARER " + tok_a}),
            ("Basic scheme", {"Authorization": "Basic " + tok_a}), ("no scheme", {"Authorization": tok_a}), ("two spaces", {"Authorization": "Bearer  " + tok_a}),
            ("trailing space", {"Authorization": "Bearer " + tok_a + " "}), ("unknown token", bearer("nope")), ("expired session", bearer(tok_expired)),
            ("inactive user", bearer(tok_gone)), ("257-char token", bearer("a" * 257)), ("256-char unknown token", bearer("a" * 256)), ("token with spaces", {"Authorization": "Bearer a b c"}),
            ("owner", bearer(tok_a)), ("viewer", bearer(tok_viewer)), ("other tenant", bearer(tok_b)), ("empty tenant", bearer(tok_c)),
        ]
        # KNOWN DIVERGENCE (HTTP stack, not route logic): uvicorn passes a header value's trailing space through, so `Bearer <valid> ` is
        # an unknown token to Python (401), while hyper trims it before axum sees it (200). Pinned here so a change is noticed; the
        # case is left out of the matrix below.
        assert (get(PY, "/owner/me", {"Authorization": "Bearer " + tok_a + " "})[0], get(RS, "/owner/me", {"Authorization": "Bearer " + tok_a + " "})[0]) == (401, 200)
        for route in OWNER_ROUTES:
            for label, hdrs in auth_cases:
                if label == "trailing space":
                    continue
                same_raw(f"{route.split('/', 2)[2][:28]} :: {label}", route, hdrs)

        # ---- per-route behaviour with valid sessions, tenant isolation and awkward data
        for token, who in ((tok_a, "A"), (tok_b, "B"), (tok_c, "C"), (tok_viewer, "viewer")):
            for route in ("/owner/phone-setup", "/owner/phone-numbers", "/owner/phone-calls", "/owner/knowledge", "/owner/email-drafts", "/owner/onboarding/authorizations",
                          "/owner/onboarding", "/owner/onboarding/readiness", "/owner/me"):
                same_raw(f"{route} as {who}", route, bearer(token))
        for status in ("draft", "approved", "discarded", "all", "", "Draft", "DRAFT", "other", "draft ", "all&status=draft", "draft&status=all", "draft&status=bogus", "a%20b", "é"):
            same_raw(f"email-drafts status={status!r}", f"/owner/email-drafts?status={status if '&' in status or '%' in status else quote(status)}", bearer(tok_a))
        same_raw("email-drafts invalid status without a session (401 beats 422)", "/owner/email-drafts?status=bogus")
        same_raw("email-drafts status as B", "/owner/email-drafts?status=all", bearer(tok_b))
        # the rows A has but B must never see, and vice versa, asserted directly as well as compared
        assert "B draft" not in json.dumps(get(RS, "/owner/email-drafts?status=all", bearer(tok_a))[1])
        assert "B SECRET" not in json.dumps(get(RS, f"/owner/crm/leads/{LA1}/transcript", bearer(tok_a))[1])
        same_raw("crm as A", "/owner/crm", bearer(tok_a))
        same_raw("crm as B", "/owner/crm", bearer(tok_b))
        crm_a = get(RS, "/owner/crm", bearer(tok_a))[1]
        assert len(crm_a["leads"]) == 4 and all(x["tenant_id"] == crm_a["leads"][0]["tenant_id"] for x in crm_a["leads"]) and len(crm_a["tasks"]) == 2, crm_a["tasks"]
        assert crm_a["calendar_url"] == "https://concierge.trendibizz.com/api/v1/calendar/ct_parity_open.ics", crm_a["calendar_url"]
        # a tenant with no calendar token: each server mints one on first read (the value is random, so only its shape is compared)
        psql("UPDATE tenants SET calendar_token=NULL WHERE slug='parity-trailing'")
        pa = get(PY, "/owner/crm", bearer(tok_c))
        assert re.fullmatch(r"https://concierge\.trendibizz\.com/api/v1/calendar/[A-Za-z0-9_-]{32}\.ics", pa[1]["calendar_url"]), pa
        psql("UPDATE tenants SET calendar_token=NULL WHERE slug='parity-trailing'")
        ra = get(RS, "/owner/crm", bearer(tok_c))
        assert re.fullmatch(r"https://concierge\.trendibizz\.com/api/v1/calendar/[A-Za-z0-9_-]{32}\.ics", ra[1]["calendar_url"]), ra
        assert pa[0] == ra[0] == 200 and {k: v for k, v in pa[1].items() if k != "calendar_url"} == {k: v for k, v in ra[1].items() if k != "calendar_url"}
        assert psql("SELECT calendar_token FROM tenants WHERE slug='parity-trailing'") in ra[1]["calendar_url"], "Rust must persist the token it minted"
        print("ANSWER: /owner/crm mints a missing calendar token on first read (both servers)")

        for who, token in (("A", tok_a), ("B", tok_b), ("C", tok_c), ("viewer", tok_viewer)):
            for lead_id in (LA1, LA2, LA3, LA4, LB1, "cccccccc-0000-4000-8000-000000000000"):
                for tail in ("transcript", "recordings"):
                    same_raw(f"lead {tail} {lead_id[:8]} as {who}", f"/owner/crm/leads/{lead_id}/{tail}", bearer(token))
        a_rows = get(RS, f"/owner/crm/leads/{LA2}/transcript", bearer(tok_a))[1]
        assert [r["content"] for r in a_rows] == ["first original <i>text</i>", "second é original"], a_rows  # falls back to enquiry_sources when there are no chat messages
        assert get(RS, f"/owner/crm/leads/{LB1}/transcript", bearer(tok_a))[0] == 404
        assert len(get(RS, f"/owner/crm/leads/{LA1}/recordings", bearer(tok_a))[1]) == 1  # the 40-day-old recording is out
        # uuid path parameter validation (pydantic's own messages) and the router's 404 for an encoded slash
        for bad in ("abc", "", "1", LA1.upper(), LA1.replace("-", ""), "{" + LA1 + "}", "urn:uuid:" + LA1, LA1 + "0", LA1[:-1], LA1.replace("-", "_", 1), "g" + LA1[1:], LA1[:8] + LA1[9:],
                    "aaaaaaa1-0000-4000-8000-00000000000g", "--------", " " + LA1, LA1 + " ", "é" * 36, "0" * 36, "x" * 32, LA1 + "-", "a-b-c-d-e"):
            for tail in ("transcript", "recordings"):
                same_raw(f"lead {tail} bad uuid {bad!r}", f"/owner/crm/leads/{quote(bad)}/{tail}", bearer(tok_a))
        same_raw("lead transcript bad uuid without a session (401 beats 422)", "/owner/crm/leads/abc/transcript")
        same_raw("lead transcript encoded slash", "/owner/crm/leads/abc%2Fdef/transcript", bearer(tok_a))
        same_raw("lead transcript encoded slash without a session (404 beats 401)", "/owner/crm/leads/abc%2Fdef/transcript")
        same_raw("lead recordings encoded slash", f"/owner/crm/leads/{LA1}%2F/recordings", bearer(tok_a))
        same_raw("lead transcript empty id", "/owner/crm/leads//transcript", bearer(tok_a))
        # phone call transcripts: ids with spaces, slashes, case, other tenants, a chat conversation with the same session id
        for who, token in (("A", tok_a), ("B", tok_b), ("C", tok_c)):
            for cid in ("CA-a1", "CA-a2", "CA-b1", quote("CA a/3 é", safe=""), "ca-a1", "CA-a1%20", "nope", "CA-a1%2F", "%2E%2E", "é"):
                same_raw(f"phone transcript {cid!r} as {who}", f"/owner/phone-calls/{cid if '%' in cid else quote(cid)}/transcript", bearer(token))
        same_raw("phone transcript empty id", "/owner/phone-calls//transcript", bearer(tok_a))
        same_raw("phone transcript encoded slash without a session (404 beats 401)", "/owner/phone-calls/a%2Fb/transcript")
        t = get(RS, "/owner/phone-calls/CA-a1/transcript", bearer(tok_a))[1]
        assert [r["content"] for r in t] == ["Hello caller <b>&", "Hi, how can I help?", "é中"], t
        # the owner boundary composes with these routes: a foreign Origin is refused before authentication, hardening headers always
        for route in ("/owner/me", "/owner/crm", "/owner/phone-calls/CA-a1/transcript", "/owner/nope"):
            for origin in ("https://evil.example", ""):
                same_raw(f"{route} origin {origin!r}", route, {**bearer(tok_a), "Origin": origin})
            for port in (PY, RS):  # an Origin equal to the server's own host is served by both
                assert get(port, route, {**bearer(tok_a), "Origin": f"http://127.0.0.1:{port}"})[0] != 403, (route, port)
        a = get_raw(RS, "/owner/me", {**bearer(tok_a), "Origin": "https://evil.example"})
        assert a[0] == 403 and a[2]["cache-control"] == "no-store", a
        a = get_raw(RS, "/owner/me", bearer(tok_a))
        assert a[0] == 200 and a[2]["cache-control"] == "no-store" and a[2]["x-content-type-options"] == "nosniff" and a[2]["referrer-policy"] == "no-referrer", a
        # a second Authorization header: Starlette's `headers.get` takes the first one
        for first, second in ((tok_a, "nope"), ("nope", tok_a)):
            conn = {}
            for port in (PY, RS):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
                c.putrequest("GET", "/owner/me")
                c.putheader("Authorization", "Bearer " + first)
                c.putheader("Authorization", "Bearer " + second)
                c.endheaders()
                r = c.getresponse()
                conn[port] = (r.status, r.read())
                c.close()
            assert conn[PY] == conn[RS], f"duplicate Authorization header: {conn}"
            n += 1


        # ---- settings-dependent rules on the alternate pairs: alt (draft workflow OFF, https base URL so the Twilio relay is "configured",
        # smsgate) and sip (Grok provider with one SIP connection for tenant A's enabled number).
        sip = json.dumps({"11111111-2222-4333-8444-555555555555": {"enabled": True, "tenant": "parity-open", "number": "+6499000001", "signing_secret": "whsec_x"},
                          "bad": {"enabled": True, "tenant": "parity-closed", "number": "+6499000003", "signing_secret": "s"}})
        start_alt_pair(procs, {"PHONE_VOICE_PROVIDER": "grok", "XAI_API_KEY": "xai-parity", "XAI_SIP_CONNECTIONS": sip, "SOCIAL_SERVICE_ENABLED": "false"}, SIP_PY, SIP_RS)
        for ports, name in (((ALT_PY, ALT_RS), "alt"), ((SIP_PY, SIP_RS), "sip")):
            for token, who in ((tok_a, "A"), (tok_b, "B"), (tok_c, "C")):
                for route in ("/owner/onboarding", "/owner/onboarding/readiness", "/owner/email-drafts", "/owner/email-drafts?status=all", "/owner/phone-calls"):
                    same_raw(f"[{name}] {route} as {who}", route, bearer(token), ports=ports)
        same_raw("[alt] email-drafts gate is checked after validation (422 beats 503)", "/owner/email-drafts?status=bogus", bearer(tok_a), ports=(ALT_PY, ALT_RS))
        same_raw("[alt] email-drafts gate is checked after the session (401 beats 503)", "/owner/email-drafts", ports=(ALT_PY, ALT_RS))
        assert get(ALT_RS, "/owner/email-drafts", bearer(tok_a))[0] == 503 and get(SIP_RS, "/owner/email-drafts", bearer(tok_a))[0] == 200
        assert get(ALT_RS, "/owner/onboarding", bearer(tok_a))[1]["channels"]["telephone"]["configured"] is True  # the Twilio relay branch
        assert get(SIP_RS, "/owner/onboarding", bearer(tok_a))[1]["channels"]["telephone"]["configured"] is True  # the SIP branch
        assert get(SIP_RS, "/owner/onboarding", bearer(tok_b))[1]["channels"]["telephone"]["configured"] is False  # key "bad" is not a canonical id
        assert get(RS, "/owner/onboarding", bearer(tok_a))[1]["channels"]["telephone"]["configured"] is False  # main pair: http base URL, legacy provider
        # the paired phone going stale flips sms: 10 seconds ago is online, 301 seconds ago is not
        psql("UPDATE sms_devices SET last_seen=now() - interval '301 seconds' WHERE token_hash='dev-parity-open'")
        same_raw("onboarding with a stale paired phone", "/owner/onboarding", bearer(tok_a))
        assert get(RS, "/owner/onboarding", bearer(tok_a))[1]["channels"]["sms"]["configured"] is False
        psql("UPDATE sms_devices SET last_seen=now() - interval '10 seconds' WHERE token_hash='dev-parity-open'")
        assert get(RS, "/owner/onboarding", bearer(tok_a))[1]["channels"]["sms"]["configured"] is True
        # a revoked session and a deactivated user stop working at once
        psql("DELETE FROM tenant_sessions WHERE token_hash='" + py_owner.digest(tok_viewer) + "'")
        same_raw("deleted session", "/owner/me", bearer(tok_viewer))
        psql("UPDATE tenant_users SET active=false WHERE email='owner-b@parity.invalid'")
        same_raw("deactivated user", "/owner/me", bearer(tok_b))
        psql("UPDATE tenant_users SET active=true WHERE email='owner-b@parity.invalid'")
        same_raw("reactivated user", "/owner/me", bearer(tok_b))
        psql("DELETE FROM tenant_users WHERE email LIKE '%@parity.invalid'")

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
