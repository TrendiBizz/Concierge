"""Batch-40 golden vectors: `GET /api/v1/unsubscribe/{token}` (`unsubscribe_page` in `main.py`).

Every expected value is the output of the LIVE `app.main.unsubscribe_page` coroutine; only the signing secret is fixed
(`unsub._secret`). Tokens are built with the real `unsub._sign`, so payloads Python's lenient `urlsafe_b64decode` accepts
(padding, stray characters, `+`) can be signed without guessing. `"error": true` means the live function raised, which
FastAPI answers with a plain 500 (a non-ASCII signature makes `hmac.compare_digest` raise `TypeError`).

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors40.py > ../concierge-stack/core-rs/parity/vectors40.json
"""
import asyncio
import base64
import json
import sys

sys.path.insert(0, ".")
from app import main, unsub  # noqa: E402

SECRET = "parity-unsub-secret"


def page(secret, token):
    unsub._secret = lambda: secret.encode()
    try:
        r = asyncio.run(main.unsubscribe_page(token))
    except Exception:  # noqa: BLE001 - a 500 in production
        return {"error": True}
    assert r.media_type == "text/html"
    return {"status": r.status_code, "body": r.body.decode("utf-8")}


def b64(raw: bytes, pad=False):
    s = base64.urlsafe_b64encode(raw).decode()
    return s if pad else s.rstrip("=")


def signed(payload):
    unsub._secret = lambda: SECRET.encode()
    return payload + "." + unsub._sign(payload)


good = unsub.make_token("tenant-1", "a@b.co") if (setattr(unsub, "_secret", lambda: SECRET.encode()) or True) else None
payload, sig = good.split(".")
raws = [b"t|c", b"tenant|a@b.co", b"|c", b"t|", b"t", b"", b"a|b|c", "é|日本".encode(), b"\xff\xfe|x", b"\x00|\x00", b"t|c\n"]
cases = [{"secret": SECRET, "token": t} for t in [
    good, "", ".", payload, payload + ".", "." + sig, good + "x", "x" + good, "!!!." + sig, sig, payload + "." + sig.upper(),
    payload + "." + sig[:-1], payload + "." + sig + ".", payload + ".é", payload + "." + sig[:-1] + "é", payload + ".日" * 2,
    "é." + sig, payload + "." + "é" * 40, " " + good, good + " ", good.replace(".", "%2E"),
]]
for raw in raws:
    for pad in (False, True):
        cases.append({"secret": SECRET, "token": signed(b64(raw, pad))})
std = base64.b64encode(b"\xfb\xff\xfe|a").decode()
for p in [std, std.rstrip("="), "dHxj" + "=", "dHxj" + "==", "dHxj" + "===", "d=Hxj", "dH xj", "dH\nxj", "dHx", "dHxj" + "A", "A", "AAAAA", "dHxj!", "!dHxj", "d-Hxj", "dH_xj",
          "dHxjAAA=" , "dHx=jA", "====", "dA==", "dA=", "dA", "dHxjdA==dA==", "déHxj", "é", "日本"]:
    cases.append({"secret": SECRET, "token": signed(p)})
cases += [{"secret": "", "token": t} for t in (good, "", "x.y")]
cases += [{"secret": "s", "token": unsub.make_token("t", "c") if False else t} for t in ("a.b",)]
for c in cases:
    c["out"] = page(c["secret"], c["token"])
print(json.dumps({"cases": cases}, ensure_ascii=False, indent=0))
