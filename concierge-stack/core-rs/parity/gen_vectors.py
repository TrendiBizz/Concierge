"""Generate golden vectors from the live Python modules. Run from the repo root's api/ directory:

    cd api && python ../concierge-stack/core-rs/parity/gen_vectors.py > ../concierge-stack/core-rs/parity/vectors.json

The Rust crate's tests must reproduce every vector exactly. Re-run this only when the Python behaviour is
deliberately changed.
"""
import json
import os
import random
import sys
from datetime import datetime, timezone

os.environ["UNSUBSCRIBE_SECRET"] = "parity-secret-not-real"
os.environ["PUBLIC_BASE_URL"] = "https://example.test/"
sys.path.insert(0, os.getcwd())

from app import chunking, contact, guard, ical, unsub  # noqa: E402

rng = random.Random(20261109)

WORDS = ["alpha", "beta", "gamma", "price", "$45.00", "café", "naïve", "日本語", "emoji😀", "x", "Dr.", "e.g.", "A?", "ok!"]


def sentence(n):
    return " ".join(rng.choice(WORDS) for _ in range(n)) + rng.choice([".", "!", "?", ""])


def paragraph():
    return (" ".join(sentence(rng.randint(1, 30)) for _ in range(rng.randint(1, 12)))).strip()


TEXTS = ["", "   ", "short", "a\n\nb", "a\n \n b", "a\n\n\n\nb", "x" * 2500, "word " * 400, "Hello.   World!\nNext? Yes.",
         "tab\t\n\t\nsplit", "日本語。" * 600, "😀" * 1200, " lead and trail ", "a.　b. c. d.", "p1\r\n\r\np2"]
TEXTS += ["\n\n".join(paragraph() for _ in range(rng.randint(1, 15))) for _ in range(15)]
chunk_cases = []
for t in TEXTS:
    for mc, ov in ((1000, 150), (200, 40), (80, 0), (300, 500), (50, 10)):
        chunk_cases.append({"text": t, "max": mc, "overlap": ov, "out": chunking.chunk_text(t, mc, ov)})

guard_cases = []
PRICES = ["$5", "$5.00", "$05.0", "$ 12", "$1,200", "$1,200.50", "$0.5", "$100.10", "$1,2", "$12,34", "$1234567", "$.5", "no price", "$9.999"]
for _ in range(300):
    reply = " ".join(rng.choice(PRICES + WORDS) for _ in range(rng.randint(0, 6)))
    evid = " ".join(rng.choice(PRICES + WORDS) for _ in range(rng.randint(0, 6)))
    guard_cases.append({"reply": reply, "evidence": evid, "unknown": sorted(str(d) for d in guard.unknown_amounts(reply, evid))})
# Decimal prints e.g. 1E+2; compare numerically in Rust via a decimal string instead.
for case in guard_cases:
    case["unknown"] = sorted(format(__import__("decimal").Decimal(x), "f") for x in case["unknown"])

phones = ["", "  ", "abc", "+64 21 123 4567", "021 123 4567", "(555) 123-4567", "15551234567", "5551234567", "+1234567", "1234567",
          "12345678", "+123456789012345", "+1234567890123456", " +64278817368 ", "0064278817368", "+", "+++1", "99999999999999999"]
contact_cases = [{"v": v, "cc": cc, "phone": contact.normalize_phone(v, cc), "key": contact.contact_key(v, cc), "email": contact.is_email(v)}
                 for v in phones + ["A@B.co", " a@b.c ", "a@b", "a b@c.d", "@x.y", "a@@b.c", "UPPER@Case.COM", "x@y.z\n"] for cc in ("1", "64")]

unsub_cases = []
for tenant, who in (("0a3e7155-2f19-4527-bee1-f2dec7b676c7", "+64278817368"), ("t", "a@b.co"), ("tenant|pipe", "x|y"), ("é", "日本")):
    tok = unsub.make_token(tenant, who)
    unsub_cases.append({"tenant": tenant, "contact": who, "token": tok, "read": list(unsub.read_token(tok) or []) or None,
                        "url": unsub.url_for(tenant, who)})
tampered = []
good = unsub.make_token("tenant", "a@b.co")
p, sig = good.split(".")
for bad in ("", ".", p, p + ".", "." + sig, p + "." + sig[:-1] + ("0" if sig[-1] != "0" else "1"), good + "x", "x" + good, "!!!." + sig):
    tampered.append({"token": bad, "read": list(unsub.read_token(bad) or []) or None})

UTC = timezone.utc
tenant = {"name": "Trendi; Bizz, Ltd"}
appts = [
    {"id": 1, "name": "Ann", "phone": "+6421", "email": "a@b.co", "notes": "Line1\nLine2, with; chars\\ and \r\n crlf", "status": "confirmed",
     "starts_at": datetime(2026, 11, 10, 10, 0, tzinfo=UTC), "ends_at": datetime(2026, 11, 10, 10, 15, tzinfo=UTC)},
    {"id": 2, "name": None, "status": "cancelled", "starts_at": datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
     "ends_at": datetime(2027, 1, 1, 0, 30, tzinfo=UTC)},
    {"id": "x-3", "name": "日本語" * 30 + " very long name to force folding " * 4, "notes": "é" * 200, "phone": "",
     "starts_at": datetime(2026, 1, 1, tzinfo=UTC), "ends_at": datetime(2026, 1, 1, 1, tzinfo=UTC)},
]
now = datetime(2026, 11, 9, 1, 2, 3, tzinfo=UTC)
ical_case = {
    "tenant": tenant["name"], "now": int(now.timestamp()),
    "appointments": [{**a, "starts_at": int(a["starts_at"].timestamp()), "ends_at": int(a["ends_at"].timestamp())} for a in appts],
    "out": ical.build(tenant, appts, now),
}
esc_cases = [{"in": s, "out": ical.esc(s)} for s in ["", "a;b,c\\d", "x\r\ny\rz\nw", "plain"]]
fold_cases = [{"in": s, "out": ical.fold(s)} for s in ["x" * 74, "x" * 75, "x" * 76, "x" * 300, "é" * 80, "日" * 60, "a" + "😀" * 40]]

print(json.dumps({"chunk": chunk_cases, "guard": guard_cases, "contact": contact_cases, "unsub": unsub_cases,
                  "unsub_tampered": tampered, "ical": ical_case, "esc": esc_cases, "fold": fold_cases,
                  "secret": "parity-secret-not-real", "base": "https://example.test/"}, ensure_ascii=False, indent=0))
