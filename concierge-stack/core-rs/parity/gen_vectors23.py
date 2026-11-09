"""Batch-23 golden vectors: the edge rules of `main.py` (owner-portal origin boundary middleware) and `security.require_admin`, from the live
functions with fake requests. No server is started.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors23.py > ../concierge-stack/core-rs/parity/vectors23.json
"""
import asyncio
import json
import sys
from types import SimpleNamespace

from fastapi import HTTPException

sys.path.insert(0, ".")
from app import main, security  # noqa: E402

out = {"boundary": [], "admin": []}
paths = ["/owner-ui", "/owner-ui/", "/owner/leads", "/owner", "/owners", "/api/v1/device-sms/jobs", "/api/v1/device-sms", "/api/v1/chat", "/admin/tenants", "/", "/owner-ui2", "/Owner/x"]
origins = [None, "", "https://c.example.com", "https://C.EXAMPLE.COM/", "http://c.example.com", "https://evil.example", "https://app.local:8443", "http://localhost:8000", "null"]
for base in ["https://c.example.com", "http://localhost:8000"]:
    main.settings.public_base_url = base
    for scheme, netloc in [("https", "c.example.com"), ("http", "localhost:8000"), ("https", "app.local:8443"), ("http", "other.example")]:
        for path in paths:
            for origin in origins:
                headers = {} if origin is None else {"origin": origin}
                req = SimpleNamespace(url=SimpleNamespace(path=path, scheme=scheme, netloc=netloc), headers=headers)

                async def call_next(r):
                    return SimpleNamespace(headers={}, status_code=200, passed=True)

                resp = asyncio.run(main.owner_boundary(req, call_next))
                out["boundary"].append({"base": base, "scheme": scheme, "netloc": netloc, "path": path, "origin": origin,
                                        "passed": bool(getattr(resp, "passed", False)), "status": resp.status_code, "headers": {k.lower(): v for k, v in dict(resp.headers).items()}})
for expected in ["", "secret", "sécret", "a" * 40]:
    for given in ["", "secret", "sécret", "Secret", "a" * 40, "a" * 39]:
        security.get_settings = lambda e=expected: SimpleNamespace(admin_token=e)
        try:
            security.require_admin(given)
            r = {"ok": True}
        except HTTPException as e:
            r = {"status": e.status_code, "detail": e.detail}
        except Exception as e:  # noqa: BLE001
            r = {"raises": type(e).__name__}
        out["admin"].append({"expected": expected, "given": given, "out": r})
json.dump(out, sys.stdout, ensure_ascii=True, separators=(",", ":"))
