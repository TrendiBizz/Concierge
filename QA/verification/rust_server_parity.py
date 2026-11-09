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

        admin_listings()

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


# ---------------------------------------------------------------------------------------------------------------------
# Read-only /admin/... listing routes (leads, campaigns, scoring, sla, tasks, pipeline, sales-summary, appointments,
# outbox, conversations, stats, email-drafts, phone-*, capabilities). Compared on the RAW response bytes (so JSON key
# order and number formatting count), status, content type and redirect target, with no redirect followed.
# ---------------------------------------------------------------------------------------------------------------------
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: D401
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def raw_get(port, path, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
    try:
        with _OPENER.open(req, timeout=30) as r:
            status, body, hdrs = r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        status, body, hdrs = e.code, e.read(), e.headers
    loc = hdrs.get("location")
    if loc:
        loc = re.sub(r"^http://127\.0\.0\.1:\d+", "http://HOST", loc)
    # access-control-allow-origin is left out: the Rust CORS layer adds it to every response, Python's only to requests that
    # carry an Origin; that difference predates these routes and is compared by the CORS case near the top of this file.
    return status, body, hdrs.get("content-type"), loc, {k: hdrs[k] for k in KEEP if k != "access-control-allow-origin" and hdrs.get(k) is not None}


UNORDERED = ("by_channel", "leads_by_status", "messages_sent", "delivery")


def _canon(raw):
    """The members of these objects come from `GROUP BY` without an ORDER BY, so their order is whatever plan PostgreSQL
    picks (asyncpg's statement cache flips from a hash to a sort aggregate after a few runs), not a property of the API:
    compare them as sets of keys. Everything else, including the order of the keys of the response itself, stays exact."""
    try:
        doc = json.loads(raw)
    except ValueError:
        return raw

    def walk(v):
        if isinstance(v, dict):
            return {k: (dict(sorted(x.items())) if k in UNORDERED and isinstance(x, dict) else walk(x)) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v

    return json.dumps(walk(doc), ensure_ascii=False, separators=(",", ":")).encode()


def adm(label, path, headers=None, pair=None, retry=False, expect=None):
    """Raw-byte comparison of the two servers. `retry` re-asks once when only a clock-dependent field could differ
    (a minute boundary crossed between the two requests): a persistent difference still fails."""
    global n
    py, rs = pair or (PY, RS)
    for attempt in (0, 1):
        a, b = raw_get(py, path, headers), raw_get(rs, path, headers)
        if a == b or not retry or attempt:
            break
    assert a[0] == b[0], f"{label}: status python={a[0]} rust={b[0]}\npython={a[1][:600]!r}\nrust  ={b[1][:600]!r}"
    if any(u in path for u in ("/stats", "/campaigns")) and a[2] == "application/json":
        a, b = (a[0], _canon(a[1])) + a[2:], (b[0], _canon(b[1])) + b[2:]
    if a[1] != b[1]:
        at = next((i for i, (x, y) in enumerate(zip(a[1], b[1])) if x != y), min(len(a[1]), len(b[1])))
        raise AssertionError(f"{label}: raw body differs at byte {at} (python {len(a[1])} bytes, rust {len(b[1])})\npython=...{a[1][max(at - 150, 0):at + 250]!r}\nrust  =...{b[1][max(at - 150, 0):at + 250]!r}")
    assert a[2:] == b[2:], f"{label}: headers python={a[2:]} rust={b[2:]}"
    if expect is not None:
        assert a[0] == expect, f"{label}: expected status {expect}, got {a[0]}"
    n += 1
    print("PASS", label, a[0])
    return a


def admin_listings():
    admin = {"X-Admin-Token": "parity-admin"}

    class Raw(str):
        pass

    def q(v):
        return "'" + v.replace("'", "''") + "'"

    def lit(v):
        if v is None:
            return "NULL"
        if isinstance(v, Raw):
            return str(v)
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        return q(v)

    def ins(table, slug, **cols):
        psql(f"INSERT INTO {table}(tenant_id,{','.join(cols)}) SELECT id,{','.join(lit(v) for v in cols.values())} FROM tenants WHERE slug={q(slug)}")

    def ago(spec):
        return Raw(f"now() - interval '{spec}'")

    # ------------------------------------------------------------------ tenants
    RICH, EMPTY, MANY, NOSLA = "parity-adm", "parity-adm-empty", "parity-adm-many", "parity-adm-nosla"
    for slug, name in ((RICH, "Adm & <Co> é"), (EMPTY, "Empty"), (MANY, "Many"), (NOSLA, "No SLA")):
        psql(f"INSERT INTO tenants(slug,name,public_key,report_token) VALUES({q(slug)},{q(name)},'pk_{slug}','rt_{slug}')")
    psql("""UPDATE tenants SET lead_value_cents=5000, sla_minutes=30, sla_min_score=50,
            scoring='{"warm_at": 20, "phone": true, "hot_at": 90, "zzz": 1, "email": "x", "booked": 1.5, "name": null, "consent": [1, {"a": "é"}]}'::jsonb
            WHERE slug='parity-adm'""")
    psql("UPDATE tenants SET lead_value_cents=2500, sla_minutes=1, sla_min_score=0, scoring='[]'::jsonb WHERE slug='parity-adm-many'")
    psql("UPDATE tenants SET lead_value_cents=0, sla_minutes=0, sla_min_score=70, scoring='\"just text\"'::jsonb WHERE slug='parity-adm-nosla'")

    # ------------------------------------------------------------------ leads of the rich tenant
    # Inserted in an order that is neither created_at order nor score order, so only an ORDER BY sorts them.
    def lead(name, **c):
        base = dict(name=name, email=f"{name.lower().replace(' ', '')}@example.com", phone="+64 21 555 0100", message="hello",
                    channel="chat", status="new", score=60, score_label="warm", score_reasons=Raw("'[]'::jsonb"),
                    value_cents=0, created_at=ago("3 hours"), updated_at=ago("3 hours"))
        base.update(c)
        ins("leads", RICH, **base)

    reasons = lambda r: Raw(f"{q(r)}::jsonb")  # noqa: E731
    lead("L old hot", score=90, score_label="hot", created_at=ago("3 hours"), score_reasons=reasons('["gave a phone number", "asked for a price", "é中"]'))
    lead("L fresh cold", score=10, score_label="cold", created_at=ago("5 minutes"))
    lead("L boundary 50", score=50, created_at=ago("45 minutes"), score_reasons=reasons('["boundary"]'))
    lead("L below 49", score=49, created_at=ago("2 hours"))
    lead("L booked", score=80, created_at=ago("2 hours"))
    lead("L cancelled appt", score=80, created_at=ago("100 minutes"), score_reasons=reasons("null"))
    lead("L alerted", score=70, created_at=ago("4 hours"), sla_alerted_at=ago("1 hour"), score_reasons=reasons('"text"'))
    lead("L eight days", score=90, created_at=ago("8 days"))
    lead("L six days", score=88, created_at=ago("6 days"), score_reasons=reasons("{}"))
    lead("L contacted", status="contacted", score=95, score_label="hot", created_at=ago("1 day"), value_cents=800)
    lead("L won", status="won", score=40, created_at=ago("5 days"), value_cents=12000, won_at=ago("2 days"), updated_at=ago("2 days"))
    lead("L won old", status="won", score=40, created_at=ago("60 days"), value_cents=7000, won_at=ago("45 days"), updated_at=ago("45 days"))
    lead("L lost", status="lost", score=20, created_at=ago("9 days"), lost_at=ago("1 day"), updated_at=ago("1 day"),
         lost_reason="too «expensive» <b>&</b>")
    lead("L won zero", status="won", score=30, created_at=ago("9 days"), value_cents=0, won_at=ago("1 day"), updated_at=ago("1 day"))
    # Two tie-breaks, each with a heap order that differs from the expected order: the pipeline sorts equal scores newest
    # first (so the older lead goes in first), the SLA list oldest first (so the newer lead goes in first).
    lead("PTie older", score=77, created_at=ago("70 minutes"))
    lead("PTie newer", score=77, created_at=ago("50 minutes"), score_reasons=reasons('["tie"]'))
    lead("STie newer", score=76, created_at=ago("55 minutes"))
    lead("STie older", score=76, created_at=ago("75 minutes"))
    lead("L young hot", score=90, created_at=ago("10 minutes"))
    lead("L completed appt", score=85, created_at=ago("2 hours"))
    lead("L negative", score=-5, score_label="cold", created_at=ago("4 days"))
    lead("Booked stage", status="booked", score=60, created_at=ago("3 days"), value_cents=300, next_action_at=ago("-2 days"))
    lead("Weird <b>&\"q\" Ünï", score=65, created_at=ago("90 minutes"), message=Raw("'line1'||chr(10)||chr(9)||chr(1)||'é中😀 \"q\" \\ back'"),
         page_url="https://x.example/?a=1&b=<2>", utm=reasons('{"b": 1, "a": [1, 2], "c": {"x": null}}'))
    lead("Numeric utm", score=61, created_at=Raw("timestamptz '2026-01-02 03:04:05.123456+00'"), utm=reasons('{"n": 1.50, "big": 12345678901234567890123, "e": 1e3}'))
    lead("No micros", score=62, created_at=Raw("timestamptz '2026-01-03 03:04:05+00'"))
    for lead_name, status, hours in (("L booked", "booked", 24), ("L cancelled appt", "cancelled", 25), ("L completed appt", "completed", -30)):
        psql(f"INSERT INTO appointments(tenant_id,lead_id,starts_at,ends_at,status) SELECT t.id,l.id,now() + interval '{hours} hours',now() + interval '{hours + 1} hours','{status}' "
             f"FROM tenants t JOIN leads l ON l.tenant_id=t.id WHERE t.slug='{RICH}' AND l.name={q(lead_name)}")
    # leads of the no-SLA tenant: plenty overdue, yet the feature is off
    ins("leads", NOSLA, name="Waiting", score=95, score_label="hot", created_at=ago("5 hours"))
    # bulk tenant: clamp edges (500 / 200 / 1000 / 100) need more rows than the clamp
    psql(f"INSERT INTO leads(tenant_id,name,score,created_at,updated_at) SELECT t.id,'bulk '||g,g%100,now() - ((1011-g)||' seconds')::interval - interval '2 minutes',now() FROM tenants t, generate_series(1,1010) g WHERE t.slug='{MANY}'")
    psql(f"INSERT INTO conversations(tenant_id,session_id,channel,started_at) SELECT t.id,'c'||g,'chat',now() - ((211-g)||' minutes')::interval FROM tenants t, generate_series(1,210) g WHERE t.slug='{MANY}'")
    psql(f"INSERT INTO outbox(tenant_id,kind,channel,to_addr,body,status,created_at) SELECT t.id,'k','sms','+1'||g,'b',CASE WHEN g%3=0 THEN 'sent' ELSE 'pending' END,now() - ((511-g)||' minutes')::interval FROM tenants t, generate_series(1,510) g WHERE t.slug='{MANY}'")
    psql(f"INSERT INTO appointments(tenant_id,starts_at,ends_at,status,name,created_at) SELECT t.id,now() + ((g)||' minutes')::interval,now() + ((g+30)||' minutes')::interval,'booked','a'||g,now() - interval '1 hour' FROM tenants t, generate_series(1,510) g WHERE t.slug='{MANY}'")
    psql(f"INSERT INTO tasks(tenant_id,title,due_at,created_at) SELECT t.id,'t'||g,now() + ((g)||' minutes')::interval,now() - ((g)||' minutes')::interval FROM tenants t, generate_series(1,205) g WHERE t.slug='{MANY}'")
    psql(f"INSERT INTO phone_calls(call_sid,tenant_id,to_number,started_at) SELECT 'CA'||g,t.id,'+64'||g,now() - ((106-g)||' minutes')::interval FROM tenants t, generate_series(1,105) g WHERE t.slug='{MANY}'")
    psql(f"INSERT INTO campaigns(tenant_id,name,channel,body,created_at) SELECT t.id,'camp '||g,'sms','b',now() - ((106-g)||' minutes')::interval FROM tenants t, generate_series(1,105) g WHERE t.slug='{MANY}'")
    psql(f"INSERT INTO email_drafts(tenant_id,sender,subject,inbound_body,reply_body) SELECT t.id,'s'||g||'@example.com','sub','in','out' FROM tenants t, generate_series(1,105) g WHERE t.slug='{MANY}'")

    # ------------------------------------------------------------------ appointments, outbox, conversations, stats data
    ins("conversations", RICH, session_id="s-old", channel="chat", started_at=ago("3 days"))
    ins("conversations", RICH, session_id="s-new", channel="sms", started_at=ago("1 hour"), pending_booking=reasons('{"when": "tomorrow"}'))
    ins("conversations", RICH, session_id="s-eval", channel="eval", started_at=ago("2 hours"))
    ins("conversations", RICH, session_id="s-mid", channel="voice", started_at=ago("1 day"), page_url="https://p.example/<x>")
    ins("conversations", RICH, session_id="s-ancient", channel="chat", started_at=ago("40 days"))
    for sess, content, role, flag, created, order in (("s-new", "third inserted first", "assistant", None, "10 minutes", 0), ("s-new", "first by time", "user", None, "50 minutes", 1),
                                                    ("s-new", "quote <b>&</b> é", "assistant", "quote_guard", "40 minutes", 2), ("s-old", "old one", "user", "quote_guard", "3 days", 3)):
        psql(f"INSERT INTO messages(conversation_id,role,content,flag,created_at) SELECT c.id,'{role}',{q(content)},{lit(flag)},now() - interval '{created}' "
             f"FROM conversations c JOIN tenants t ON t.id=c.tenant_id WHERE t.slug='{RICH}' AND c.session_id='{sess}'")
    for status, name, start, created in (("booked", "Early", "-3 days", "3 days"), ("cancelled", "Zoë Ñandú <b>", "5 days", "2 days"), ("booked", "Mid", "1 day", "10 days"),
                                         ("completed", "", "-10 days", "1 hour"), ("no_show", "Ünï", "2 hours", "20 days")):
        ins("appointments", RICH, starts_at=ago(start.lstrip("-")) if start.startswith("-") else Raw(f"now() + interval '{start}'"), ends_at=Raw("now() + interval '10 days'"),
            status=status, name=name, notes=Raw("'n'||chr(10)||'<i>&'"), created_at=ago(created))
    ins("appointments", RICH, starts_at=Raw("timestamptz '2026-03-04 05:06:07.5+00'"), ends_at=Raw("timestamptz '2026-03-04 06:06:07+00'"), status="booked", name="fixed")
    for i, (kind, status, created, last_error, sent) in enumerate((("reminder", "sent", "1 day", "", "1 day"), ("owner_alert", "failed", "2 hours", "boom <&> é", None),
                                                              ("campaign", "pending", "10 days", "", None), ("reminder", "sent", "5 days", "", "5 days"), ("reminder", "cancelled", "1 hour", "", None))):
        ins("outbox", RICH, kind=kind, channel="email" if i % 2 else "sms", to_addr=f"to{i}@example.com", subject=Raw("'s'||chr(10)"), body="b", status=status, attempts=i,
            last_error=last_error, created_at=ago(created), send_at=ago(created), sent_at=ago(sent) if sent else None)
    ins("tasks", RICH, title="No due, created late", due_at=None, created_at=ago("1 hour"))
    ins("tasks", RICH, title="Due far", due_at=Raw("now() + interval '10 days'"), created_at=ago("2 hours"))
    ins("tasks", RICH, title="Overdue <b>&</b> é", notes="n", due_at=ago("2 days"), created_at=ago("3 hours"))
    ins("tasks", RICH, title="No due, created early", due_at=None, created_at=ago("9 hours"))
    ins("tasks", RICH, title="Done long ago", status="done", completed_at=ago("20 days"), created_at=ago("30 days"), due_at=ago("21 days"))
    ins("tasks", RICH, title="Done no completed_at", status="done", completed_at=None, created_at=ago("2 hours"))
    ins("tasks", RICH, title="Done recently", status="done", completed_at=ago("1 hour"), created_at=ago("5 days"))
    psql(f"INSERT INTO tasks(tenant_id,lead_id,title,kind,due_at) SELECT t.id,l.id,'Follow up: lead','follow_up',now() - interval '1 hour' FROM tenants t JOIN leads l ON l.tenant_id=t.id WHERE t.slug='{RICH}' AND l.name='L old hot'")
    for frm, to, ago_ in (("new", "contacted", "1 day"), ("contacted", "booked", "2 days"), ("booked", "won", "3 days"), ("new", "lost", "1 day"), ("new", "lost", "2 days"),
                          ("new", "contacted", "40 days"), ("contacted", "lost", "50 days"), ("new", "contacted", "6 days")):
        psql(f"INSERT INTO lead_events(lead_id,tenant_id,from_status,to_status,created_at) SELECT l.id,t.id,'{frm}','{to}',now() - interval '{ago_}' FROM tenants t JOIN leads l ON l.tenant_id=t.id WHERE t.slug='{RICH}' AND l.name='L won'")

    # campaigns: created_at order is the reverse of id order; filters in awkward shapes; delivery rows on the first
    camp_filters = ('{"statuses": ["new", "lost"], "min_score": 0, "older_than_days": 30, "max_recipients": 200}', "{}", '{"n": 1.50, "s": "é <b>"}', "[]")
    for i, f in enumerate(camp_filters):
        ins("campaigns", RICH, name=f"Camp {i} é <b>&", channel="email" if i % 2 else "sms", subject=Raw("'sub'"), body="Hi {first}", filters=reasons(f),
            status="queued" if i == 0 else "draft", recipient_count=i, created_at=ago(f"{4 - i} days"), queued_at=ago("1 hour") if i == 0 else None)
    for status, count in (("sent", 3), ("failed", 1), ("pending", 2), ("cancelled", 1)):
        for _ in range(count):
            psql(f"INSERT INTO outbox(tenant_id,kind,channel,to_addr,body,status,campaign_id) SELECT t.id,'campaign','sms','+1','b','{status}',(SELECT min(id) FROM campaigns WHERE tenant_id=t.id) FROM tenants t WHERE t.slug='{RICH}'")
    camp_ids = [int(x) for x in psql(f"SELECT id FROM campaigns WHERE tenant_id=(SELECT id FROM tenants WHERE slug='{RICH}') ORDER BY id").split("\n")]
    # phone
    ins("managed_phone_setups", RICH, designated_number="+64 9 555 0100", connection="existing_sip", answer_mode="unanswered", owner_number="+64 21 555 0101", status="active")
    ins("managed_phone_setups", NOSLA, designated_number="+6", connection="mobile_forwarding", answer_mode="all_calls", owner_number="+7", status="requested")
    psql("INSERT INTO phone_numbers(e164,tenant_id,enabled,created_at) SELECT '+6421555'||g,t.id,g%2=0,now() - ((g*7%5)||' hours')::interval FROM tenants t, generate_series(1,4) g WHERE t.slug='parity-adm'")
    psql("INSERT INTO phone_numbers(e164,tenant_id,enabled) SELECT '+99',t.id,true FROM tenants t WHERE t.slug='parity-adm-nosla'")
    for sid, ago_, ended in (("CA-old", "3 days", "3 days"), ("CA-new", "1 hour", None), ("CA-mid", "1 day", "1 day")):
        ins("phone_calls", RICH, call_sid=sid, from_number="", to_number="+64 9 555 0100", status="completed" if ended else "ringing", started_at=ago(ago_), ended_at=ago(ended) if ended else None)
    # email drafts: ids ascending, DESC expected; statuses mixed
    for i, (status, approved) in enumerate((("draft", None), ("approved", "1 hour"), ("discarded", None), ("draft", None), ("approved", "2 days"))):
        ins("email_drafts", RICH, sender=f"cust{i}@example.com", subject=f"Re: é {i} <b>", inbound_body="in &", reply_body="out\nline <i>", status=status,
            source_id=None if i % 2 else f"src{i}", approved_at=ago(approved) if approved else None)

    # ------------------------------------------------------------------ servers with the email-draft feature on
    procs = []
    PY2, RS2 = PY + 2, RS + 2
    on = {**os.environ, **ENV, "EMAIL_DRAFTS_ENABLED": "true"}
    try:
        procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PY2)], cwd=ROOT / "api", env=on,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        procs.append(subprocess.Popen([str(BIN)], env={**on, "BIND": f"127.0.0.1:{RS2}"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        wait(PY2)
        wait(RS2)
        _admin_cases(admin, RICH, EMPTY, MANY, NOSLA, camp_ids, (PY2, RS2))
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


def _admin_cases(admin, RICH, EMPTY, MANY, NOSLA, camp_ids, on_pair):
    slugs = (RICH, EMPTY, MANY, NOSLA, "missing")
    SLUG_ROUTES = ["leads", "campaigns", "scoring", "sla", "tasks", "pipeline", "sales-summary", "appointments", "outbox", "conversations",
                   "stats", "email-drafts", "phone-setup", "phone-numbers", "phone-calls"]
    TIMED = {"sla", "sales-summary", "stats", "pipeline"}  # carry a clock-dependent field

    # --- capabilities and the gate, on every route
    adm("capabilities", "/admin/capabilities", admin, expect=200)
    adm("capabilities (feature on)", "/admin/capabilities", admin, pair=on_pair, expect=200)
    adm("capabilities no token", "/admin/capabilities")
    adm("capabilities wrong token", "/admin/capabilities", {"X-Admin-Token": "nope"})
    adm("capabilities empty token", "/admin/capabilities", {"X-Admin-Token": ""})
    for route in SLUG_ROUTES:
        base = f"/admin/tenants/{RICH}/{route}"
        adm(f"{route}: no token", base)
        adm(f"{route}: wrong token", base, {"X-Admin-Token": "nope"})
        adm(f"{route}: no token beats a bad query (401 before 422)", base + "?limit=abc&days=abc&status=zzz&min_score=q")
        adm(f"{route}: unknown slug", f"/admin/tenants/missing/{route}", admin)
        adm(f"{route}: unknown slug, no token", f"/admin/tenants/missing/{route}")
        adm(f"{route}: encoded slash in slug (404 beats 401)", f"/admin/tenants/parity%2Fadm/{route}")
        adm(f"{route}: encoded slash in slug with token", f"/admin/tenants/parity%2Fadm/{route}", admin)
        adm(f"{route}: trailing slash", base + "/", admin)
        adm(f"{route}: trailing slash, no token", base + "/")
        adm(f"{route}: trailing slash with query", base + "/?limit=2", admin)
        adm(f"{route}: two trailing slashes", base + "//", admin)
        adm(f"{route}: doubled slash inside", f"/admin/tenants//{RICH}/{route}", admin)
        adm(f"{route}: leading doubled slash", f"//admin/tenants/{RICH}/{route}", admin)
        adm(f"{route}: slug case matters", f"/admin/tenants/{RICH.upper()}/{route}", admin)
        adm(f"{route}: empty slug", f"/admin/tenants//{route}", admin)
        adm(f"{route}: POST-only sibling path is not this route", base + "x", admin)
    # --- every route against every kind of tenant, default parameters
    for route in SLUG_ROUTES:
        for slug in slugs:
            adm(f"{route} {slug}", f"/admin/tenants/{slug}/{route}", admin, retry=route in TIMED)
    # --- the feature gate of the email drafts
    adm("email-drafts feature off (503 before the tenant lookup)", "/admin/tenants/missing/email-drafts", admin, expect=503)
    adm("email-drafts feature off, bad status (422 before 503)", f"/admin/tenants/{RICH}/email-drafts?status=zzz", admin, expect=422)
    for slug in slugs:
        for status in ("", "?status=draft", "?status=approved", "?status=discarded", "?status=all", "?status=ALL", "?status=", "?status=nope", "?status=draft&status=all"):
            adm(f"email-drafts (on) {slug}{status}", f"/admin/tenants/{slug}/email-drafts{status}", admin, pair=on_pair)
    adm("email-drafts (on) no token", f"/admin/tenants/{RICH}/email-drafts", pair=on_pair)
    adm("email-drafts (on) bad status, unknown slug (422 before 404)", "/admin/tenants/missing/email-drafts?status=zzz", admin, pair=on_pair)
    adm("email-drafts (on) unknown slug", "/admin/tenants/missing/email-drafts", admin, pair=on_pair)
    # --- integer query parameters: limit clamps, bad values, pydantic's integer rules
    INTS = ["", "=", "=1", "=0", "=-3", "=2", "=3", "=50", "=99", "=100", "=101", "=199", "=200", "=201", "=499", "=500", "=501", "=100000",
            "=abc", "=1.0", "=1.5", "=1e2", "=0x10", "=%20%207%20", "=+7", "=%2B7", "=1_0", "=01", "=%D9%A3", "=1000000000000000000000000", "=-1000000000000000000000000",
            "=9223372036854775807", "=9223372036854775808", "=%FF", "=%zz", "=true", "=1&limit=2", "=2&limit=abc"]
    for route, names in (("leads", ("limit",)), ("appointments", ("limit",)), ("outbox", ("limit",)), ("conversations", ("limit",)),
                         ("stats", ("days",)), ("sales-summary", ("days",))):
        for slug in (RICH, MANY):
            for name in names:
                for v in INTS:
                    adm(f"{route} {slug} ?{name}{v}", f"/admin/tenants/{slug}/{route}?{name}{v}", admin, retry=route in TIMED)
        adm(f"{route}: unknown slug with a bad value (422 before 404)", f"/admin/tenants/missing/{route}?{names[0]}=abc", admin)
        adm(f"{route}: unrelated parameter ignored", f"/admin/tenants/{RICH}/{route}?other=1&{names[0]}=2", admin, retry=route in TIMED)
        adm(f"{route}: parameter names are case-sensitive", f"/admin/tenants/{RICH}/{route}?{names[0].upper()}=2", admin, retry=route in TIMED)
    for v in ("=50", "=-4", "=-10", "=-6", "=-5", "=0", "=49", "=60", "=100", "=101", "=abc", "=", "=2147483647", "=2147483648", "=-2147483649", "=99999999999999999999999", "=1.5", "=%20%2050%20"):
        for slug in (RICH, MANY):
            adm(f"leads {slug} ?min_score{v}", f"/admin/tenants/{slug}/leads?min_score{v}", admin)
    for q_ in ("?limit=abc&min_score=zzz", "?min_score=zzz&limit=abc", "?limit=2&min_score=50", "?limit=1&min_score=-1", "?limit=0&min_score=1e3", "?limit=9&min_score=2147483648"):
        adm(f"leads two parameters {q_}", f"/admin/tenants/{RICH}/leads{q_}", admin)
    # --- appointments status filter
    for st in ("", "?status=booked", "?status=cancelled", "?status=completed", "?status=no_show", "?status=", "?status=BOOKED", "?status=nope", "?status=%C3%A9",
               "?status=booked&limit=1", "?limit=2&status=booked", "?status=booked&status=cancelled", "?status=%20booked"):
        for slug in (RICH, MANY, EMPTY):
            adm(f"appointments {slug}{st}", f"/admin/tenants/{slug}/appointments{st}", admin)
    # --- tasks
    for st in ("", "?status=open", "?status=done", "?status=all", "?status=", "?status=OPEN", "?status=nope", "?status=open&status=done", "?status=done&status=nope", "?status=%C3%A9", "?status=a%20b"):
        for slug in (RICH, MANY, EMPTY):
            adm(f"tasks {slug}{st}", f"/admin/tenants/{slug}/tasks{st}", admin)
    # --- campaigns by id
    cid = camp_ids[0]
    for path in [f"/admin/campaigns/{c}" for c in camp_ids] + [
            f"/admin/campaigns/{cid}/", f"/admin/campaigns/{cid}//", f"/admin/campaigns/{cid}?x=1", "/admin/campaigns/0", "/admin/campaigns/-1", "/admin/campaigns/999999999",
            "/admin/campaigns/abc", "/admin/campaigns/1.5", "/admin/campaigns/1.0", f"/admin/campaigns/%20{cid}%20", f"/admin/campaigns/%2B{cid}", f"/admin/campaigns/0{cid}",
            f"/admin/campaigns/{cid}_0", "/admin/campaigns/9223372036854775807", "/admin/campaigns/9223372036854775808", "/admin/campaigns/-9223372036854775809",
            "/admin/campaigns/1000000000000000000000000", "/admin/campaigns/%D9%A3", "/admin/campaigns/%2F", f"/admin/campaigns/{cid}%2F", "/admin/campaigns/",
            "/admin/campaigns//", f"//admin/campaigns/{cid}", "/admin/campaigns/%FF", "/admin/campaigns/true", "/admin/campaigns/1e2", "/admin/campaigns/%C3%A9"]:
        adm(f"campaign {path}", path, admin)
        adm(f"campaign no token {path}", path)
    adm("campaign wrong token", f"/admin/campaigns/{cid}", {"X-Admin-Token": "nope"})
    # delivery of a campaign in the bulk tenant (no outbox rows) and one cross-tenant read
    many_ids = psql(f"SELECT id FROM campaigns WHERE tenant_id=(SELECT id FROM tenants WHERE slug='{MANY}') ORDER BY id LIMIT 2").split("\n")
    for i in many_ids:
        adm(f"campaign of another tenant {i}", f"/admin/campaigns/{i}", admin)
    # --- sales summary / stats extra
    adm("stats days=1 vs days=2 differ in daily rows", f"/admin/tenants/{RICH}/stats?days=2", admin, retry=True)
    # --- the redirect itself is compared, not followed; Location is the decoded, stripped path re-quoted by RedirectResponse
    for tricky in ("/admin/tenants/a%20b/leads/?x=%41%20b", "/admin/tenants/%C3%A9/leads/", "/admin/tenants/a%25b/leads/", "/admin/tenants/a+b/leads//",
                   "/admin/tenants/a%3Fb/sla/", "/admin/tenants/a%23b%5Cc/sla/", "/admin/tenants/a%27%22%3B%26%3D/sla/", "/admin/tenants/x%2Fy/leads/", "/admin/campaigns/7%2F"):
        adm(f"redirect {tricky}", tricky, admin, expect=307 if "x%2Fy" not in tricky else 404)
    # Known divergence (see PORT_STATUS Batch 28): Starlette routes the DECODED path, so an encoded slash can make one
    # segment into two and select a sibling route (`/admin/tenants/x%2Fleads` is the leads route of tenant `x`). The Rust
    # router sees one segment and answers its 404. Recorded here so a future fix has to update this line.
    alias = "/admin/tenants/parity-adm%2Fleads"
    assert raw_get(PY, alias, admin)[0] == 200 and raw_get(RS, alias, admin)[0] == 404, "encoded-slash aliasing changed: update PORT_STATUS"
    alias = "/admin/campaigns%2F" + str(camp_ids[0])
    assert raw_get(PY, alias, admin)[0] == 200 and raw_get(RS, alias, admin)[0] == 404, "encoded-slash aliasing changed: update PORT_STATUS"
    r = raw_get(PY, f"/admin/tenants/{RICH}/leads/?limit=2", admin)
    assert r[0] == 307 and r[3] == f"http://HOST/admin/tenants/{RICH}/leads?limit=2", r
    # --- the raw-byte comparison would be vacuous if the body were not JSON the handler made: spot-check shapes
    body = json.loads(raw_get(PY, f"/admin/tenants/{RICH}/sla", admin)[1])
    assert body["sla_minutes"] == 30 and len(body["waiting"]) >= 5, body
    body = json.loads(raw_get(PY, f"/admin/tenants/{RICH}/stats", admin)[1])
    assert body["conversations"] >= 3 and body["leads"] >= 10 and body["quote_guard_interventions"] == 2, body


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
