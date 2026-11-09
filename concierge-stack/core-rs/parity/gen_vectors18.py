"""Batch-18 golden vectors: `social_bridge` from the live module with a fake `httpx` client and a recording fake `_request`.
No network is used, no social account is touched.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors18.py > ../concierge-stack/core-rs/parity/vectors18.json
Also writes src/social_safe_errors.json (the audited message allow-lists, read from the Python source, not retyped).
"""
import ast
import asyncio
import json
import random
import sys
from types import SimpleNamespace

import httpx
from fastapi import HTTPException

sys.path.insert(0, ".")
from app import social_bridge as sb  # noqa: E402

rng = random.Random(20261125)
out = {}

# ---- audited allow-lists straight from the source ------------------------------------------------------------------------
tree = ast.parse(open("app/social_bridge.py").read())
sets = {}
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Set) and isinstance(node.targets[0], ast.Name):
        sets[node.targets[0].id] = [e.value for e in node.value.elts]
json.dump({"safe": sets["safe"], "safe_linkedin": sets["safe_linkedin"]}, open("../concierge-stack/core-rs/src/social_safe_errors.json", "w"), ensure_ascii=True, indent=0)

# ---- configuration ---------------------------------------------------------------------------------------------------------
cfg = []
urls = ["http://127.0.0.1:4390", "http://localhost:4390/", "http://host.docker.internal:5000", "https://127.0.0.1:4390", "http://example.com:4390", "http://127.0.0.1",
        "http://127.0.0.1:80", "http://127.0.0.1:1023", "http://127.0.0.1:1024", "http://127.0.0.1:4390/x", "http://127.0.0.1:4390?x=1", "http://127.0.0.1:4390#f",
        "http://u:p@127.0.0.1:4390", "http://u@127.0.0.1:4390", "http://127.0.0.1:99999", "http://127.0.0.1:abc", "HTTP://LOCALHOST:4390", "http://127.0.0.1:4390//",
        "", "http://[::1]:4390", "http://:4390", "http://127.0.0.1:0"]
for enabled in (True, False):
    for key in ("", "k" * 31, "k" * 32, "k" * 40):
        for url in urls:
            sb.get_settings = lambda e=enabled, k=key, u=url: SimpleNamespace(social_service_enabled=e, social_concierge_key=k, social_service_url=u)
            try:
                r = {"ok": list(sb._configuration())}
            except HTTPException as e:
                r = {"status": e.status_code, "detail": e.detail}
            except ValueError as e:
                r = {"raises": "ValueError"}
            cfg.append({"enabled": enabled, "key": key, "url": url, "out": r})
out["config"] = cfg

# ---- _request status mapping ----------------------------------------------------------------------------------------------
KEY = "k" * 40
sb.get_settings = lambda: SimpleNamespace(social_service_enabled=True, social_concierge_key=KEY, social_service_url="http://127.0.0.1:4390")
log = {}


class Resp:
    def __init__(self, status, body, raw):
        self.status_code, self._body, self._raw = status, body, raw

    def json(self):
        if self._raw == "invalid":
            raise ValueError("bad json")
        return self._body


class FakeClient:
    spec = None

    def __init__(self, timeout=None, follow_redirects=None):
        log["timeout"], log["redirects"] = timeout, follow_redirects

    async def __aenter__(self):
        return self

    async def __aexit__(self, *e):
        return False

    async def request(self, method, url, headers=None, json=None):
        log["call"] = [method, url, headers, json]
        if FakeClient.spec == "error":
            raise httpx.ConnectError("down")
        return Resp(*FakeClient.spec)


sb.httpx.AsyncClient = FakeClient
safe = sets["safe"]
safe_li = sets["safe_linkedin"]
paths = ["/v1/customers/a/rules", "/v1/customers/a/compose", "/v1/customers/a/posts/x/media", "/v1/customers/a/media", "/v1/customers/a/oauth/meta/facebook/finish",
         "/v1/customers/a/oauth/linkedin/finish", "/v1/customers/a/oauth/tiktok/finish", "/v1/oauth/providers", "/v1/customers/a/oauth/linkedin_organization/finish"]
req = []
statuses = [200, 201, 204, 299, 300, 301, 400, 401, 404, 409, 429, 500, 502]
bodies = [None, {"error": safe[0]}, {"error": safe_li[0]}, {"error": "Something else"}, {"error": 5}, [1], "text", {"x": 1}, {"error": None}, {"error": safe[-1]}, {"error": safe_li[-1]}]
for p in paths:
    for st in statuses:
        for b in bodies:
            for raw in (None, "invalid"):
                if raw and rng.random() > 0.2:
                    continue
                FakeClient.spec = (st, b, raw)
                try:
                    r = {"ok": asyncio.run(sb._request("POST", p, {"a": 1}))}
                except HTTPException as e:
                    r = {"status": e.status_code, "detail": e.detail}
                except (AttributeError, ValueError) as e:
                    r = {"raises": type(e).__name__}
                req.append({"path": p, "status": st, "body": b, "raw": raw, "out": r, "timeout": log["timeout"], "redirects": log["redirects"], "call": log["call"]})
for p in paths[:3]:
    FakeClient.spec = "error"
    try:
        r = {"ok": asyncio.run(sb._request("GET", p))}
    except HTTPException as e:
        r = {"status": e.status_code, "detail": e.detail}
    req.append({"path": p, "status": "error", "body": None, "raw": None, "out": r, "timeout": log["timeout"], "redirects": log["redirects"], "call": log.get("call")})
out["request"] = req

# ---- operations over a recording fake _request ---------------------------------------------------------------------------
ops_out = []
GOOD_ID = "A" * 16
BAD_IDS = ["", "short", "A" * 15, "A" * 129, "A" * 16 + "\n", "é" * 20, "a b" * 6, "ok_ok-ok_ok-ok-1"]
CODES = ["c", "", "x" * 2048, "x" * 2049]
SLUGS = ["acme", "a", "Acme", "-a", "a" * 101, "a" * 102, "a_b", "a-b-1", "", "é"]
OPS = [
    ("ensure_tenant", lambda: ()), ("provider_status", lambda: ()), ("accounts", lambda: ()), ("posts", lambda: ()),
    ("compose", lambda: ({"p": 1},)),
    ("submit_draft", lambda: (rng.choice([GOOD_ID] + BAD_IDS),)),
    ("request_approval", lambda: (rng.choice([GOOD_ID] + BAD_IDS), rng.choice([0, 1700000000]))),
    ("decide", lambda: (rng.choice([GOOD_ID] + BAD_IDS), rng.choice([True, False]))),
    ("renew_social_token", lambda: (rng.choice([GOOD_ID] + BAD_IDS),)),
    ("start_meta_oauth", lambda: (rng.choice(["facebook", "instagram", "x", ""]),)),
    ("finish_meta_oauth", lambda: (rng.choice(["facebook", "instagram", "x"]), rng.choice([GOOD_ID] + BAD_IDS), rng.choice(CODES))),
    ("unlink_meta", lambda: (rng.choice(["facebook", "instagram", "x"]), rng.choice([GOOD_ID] + BAD_IDS))),
    ("create_draft", lambda: (rng.choice(["post", "", "  ", "x" * 10000, "x" * 10001]), rng.choice([[GOOD_ID], [], [GOOD_ID] * 10, [GOOD_ID] * 11, [GOOD_ID, "bad"]]),
                              rng.choice(["", "https://l"]), rng.choice(["", "#t"]),
                              rng.choice([None, [], ["https://m/x.png"], ["http://m"], ["upload:" + "A" * 20], ["upload:" + "A" * 19], ["https://" + "x" * 2041], ["https://m"] * 11, [5]]),
                              rng.choice([None, {}, {"o": 1}]))),
]
for prov in ["tiktok", "google", "x", "mastodon", "linkedin"]:
    OPS.append((f"start_{prov}_oauth", lambda: ()))
    OPS.append((f"finish_{prov}_oauth", lambda: (rng.choice([GOOD_ID] + BAD_IDS), rng.choice(CODES))))
OPS.append(("start_linkedin_organization_oauth", lambda: ()))
OPS.append(("finish_linkedin_organization_oauth", lambda: (rng.choice([GOOD_ID] + BAD_IDS), rng.choice(CODES))))
for prov, fn in [("tiktok", "disconnect_tiktok"), ("google", "disconnect_google"), ("x", "disconnect_x"), ("mastodon", "disconnect_mastodon"), ("linkedin", "unlink_linkedin")]:
    OPS.append((fn, lambda: (rng.choice([GOOD_ID] + BAD_IDS),)))

for case in range(900):
    name, mk = rng.choice(OPS)
    args = mk()
    tenant = {"slug": rng.choice(SLUGS) if rng.random() < 0.25 else "acme", "name": rng.choice(["Acme", "Ünï"])}
    script = {"rules": rng.choice([{"ok": 1}] * 4 + [(404,), (500,), (503,)]), "create": rng.choice([{"ok": 1}] * 3 + [(400,), (409,), (500,)]), "again": rng.choice([{"ok": 1}, (404,), (503,)]),
              "main": rng.choice([{"ok": 1}] * 5 + [(502,), (503,), (400,)])}
    calls = []
    state = {"rules_seen": 0}

    async def fake(method, path, data=None, script=script, calls=calls, state=state):
        calls.append([method, path, data])
        if path.endswith("/rules"):
            key = "rules" if state["rules_seen"] == 0 else "again"
            state["rules_seen"] += 1
        elif path == "/v1/customers" and method == "POST":
            key = "create"
        else:
            key = "main"
        r = script[key]
        if isinstance(r, tuple):
            raise HTTPException(r[0], "scripted")
        return {"result": key}

    sb._request = fake
    try:
        res = {"ok": asyncio.run(getattr(sb, name)(*(args if name == "provider_status" else (tenant, *args))))}
    except HTTPException as e:
        res = {"status": e.status_code, "detail": e.detail}
    ops_out.append({"op": name, "args": list(args), "tenant": tenant, "script": script, "out": res, "calls": calls})
out["ops"] = ops_out
json.dump(out, sys.stdout, ensure_ascii=True, separators=(",", ":"))
