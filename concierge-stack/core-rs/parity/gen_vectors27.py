"""Batch-27 golden vectors: the sandbox demo page, `GET /demo/{slug}` (`demo_page` in `main.py`).

Every expected value is the output of the LIVE `app.main.demo_page` coroutine. Only its two inputs are stubbed: the tenant
lookup (`tenants.get_by_slug`) and the first-chunk query (`db.pool().fetchval`). The tenant dict is what `tenants._load`
returns, so `demo_questions` is already decoded once; a value that is still text exercises the second `json.loads`.
When the live function raises (FastAPI answers a plain 500) the vector records `"error": true`.

`"declined": true` marks the one input Python accepts but the Rust port deliberately refuses (a non-empty JSON object in
`demo_questions`: Python iterates its keys in PostgreSQL's jsonb order). The Rust test asserts it fails closed.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors27.py > ../concierge-stack/core-rs/parity/vectors27.json
"""
import asyncio
import json
import sys

sys.path.insert(0, ".")
from app import main  # noqa: E402


class FakePool:
    def __init__(self, excerpt):
        self.excerpt = excerpt

    async def fetchval(self, sql, *args):
        assert "FROM chunks" in sql
        return self.excerpt


def run(tenant, excerpt, presenter):
    async def fake_get_by_slug(slug):
        return tenant

    main.tenants.get_by_slug = fake_get_by_slug
    main.db.pool = lambda: FakePool(excerpt)
    try:
        response = asyncio.run(main.demo_page("any", presenter))
    except Exception:  # noqa: BLE001 - a 500 in production
        return {"error": True}
    assert response.status_code == 200 and response.media_type == "text/html"
    return {"out": response.body.decode("utf-8")}


def base(**over):
    t = {"id": "00000000-0000-0000-0000-000000000001", "name": "Open Co", "accent_color": "#2563eb",
         "site_url": "https://open.example", "public_key": "pk_open", "demo_questions": []}
    t.update(over)
    return t


QUESTION_SHAPES = [
    [], ["What are your hours?", "Do you book online?"], ["Q & <b>A</b>", 'say "hi"', "it's", "é中"],
    ["one"], [""], ["a\nb"], None, 0, 5, True, False, 0.0, 1.5, [1, 2], ["ok", 2], [["nested"]], [None],
    "", "[]", '["a", "b"]', '["x & y"]', '"abc"', "not json", "0", "null", "5", "true", "[1]", '{"k": "v"}', "{}",
    "é中", {"a": 1}, {},
]
EXCERPTS = [None, "", "short", "line1\nline2\r\nline3", "x" * 700, "x" * 701, "é" * 701, "<b>&</b>" * 200, "\n" * 5, "ab\n" * 400,
            "𝔘" * 702, "it's \"quoted\" & <tagged>"]
SITES = [None, "", "https://open.example", "http://b.example/?x=1&y=2", "ftp://x.example", "HTTPS://UPPER.example",
         " https://leading-space.example", "https://<b>&\"'", "httpx://no", "http://"]
NAMES = ["Open Co", "Ünï & Co", "<script>\"x\"'</script>", ""]
ACCENTS = ["#2563eb", '"><script>alert(1)</script>', "Ünï & Co", "", "red;background:url(x)"]
PRESENTERS = [0, 1, 2, -1, 7, 10**18, -(10**18)]

out = {"cases": []}


def add(tenant, excerpt, presenter, note):
    result = run(tenant, excerpt, presenter)
    effective = tenant.get("demo_questions")
    if isinstance(effective, str):  # demo_page decodes text a second time, so an object may arrive as text
        try:
            effective = json.loads(effective)
        except ValueError:
            effective = None
    if "error" not in result and isinstance(effective, dict) and effective and presenter != 0:
        result["declined"] = True
    out["cases"].append({"note": note, "tenant": tenant, "excerpt": excerpt, "presenter": presenter, **result})


# every question shape under every presenter value, the rest held at defaults
for qs in QUESTION_SHAPES:
    for p in PRESENTERS:
        add(base(demo_questions=qs), "Hello\nWorld", p, "questions")
for ex in EXCERPTS:
    for p in (0, 1):
        add(base(demo_questions=["Q1?", "Q2?"]), ex, p, "excerpt")
for site in SITES:
    add(base(site_url=site), "e", 0, "site_url")
for name in NAMES:
    add(base(name=name), "e", 1, "name")
for accent in ACCENTS:
    add(base(accent_color=accent), "e", 1, "accent")
add(base(public_key="pk_<\"&'>"), "e", 0, "public_key escaping")
# a site_url key that is absent altogether, and fields Python cannot escape
no_site = base()
del no_site["site_url"]
add(no_site, "e", 0, "site_url absent")
for field in ("name", "accent_color", "public_key"):
    missing = base()
    del missing[field]
    add(missing, "e", 0, f"{field} absent")
    add(base(**{field: None}), "e", 0, f"{field} null")
    add(base(**{field: 5}), "e", 0, f"{field} number")
no_q = base()
del no_q["demo_questions"]
add(no_q, "e", 1, "demo_questions absent")

print(json.dumps(out, ensure_ascii=False, indent=1))
