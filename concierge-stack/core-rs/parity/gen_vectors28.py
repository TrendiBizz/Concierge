"""Batch-28 golden vectors: Starlette's `FileResponse`, as `main.py` uses it for the static pages.

Every expected value comes from the LIVE starlette in the venv:
 - ETag / Last-Modified / mtime text from `os.stat` on REAL files whose size and nanosecond mtime are set here;
 - `FileResponse._parse_range_header(header, size)` (a classmethod) for a few hundred Range headers x file sizes;
 - `FileResponse._should_use_range` for If-Range values, on an instance with fixed validators;
 - `generate_multipart`'s precomputed content length and part header.
`"declined": true` marks a Range header with non-ASCII, non-whitespace text: the Rust port must either match Python exactly
(when no digit is parsed) or refuse with `Unsupported`; it must never produce a different answer.

    cd api && PYTHONPATH=../QA/verification/shims:. python -I ../concierge-stack/core-rs/parity/gen_vectors28.py > ../concierge-stack/core-rs/parity/vectors28.json
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, ".")
from starlette.responses import FileResponse, MalformedRangeHeader, RangeNotSatisfiable  # noqa: E402

out = {"stat": [], "range": [], "if_range": [], "multipart": []}

# 1. stat headers from real files
with tempfile.TemporaryDirectory() as d:
    for size, ns in [
        (0, 0), (1, 1), (29430, 1794219280470824189), (80022, 1794219280000000000), (5, 1700000000999999999),
        (46905, 1700000000100000000), (7, 1234567890123456789), (123456789, 1999999999000000001),
        (3, 1600000000500000000), (10, 1762683240000000001), (100, 1762683240999999999), (65536, 1500000000000000007),
    ]:
        path = os.path.join(d, "f")
        with open(path, "wb") as fh:
            fh.write(b"x" * size)
        os.utime(path, ns=(ns, ns))
        st = os.stat(path)
        assert st.st_mtime_ns == ns and st.st_size == size
        r = FileResponse(path, stat_result=st)
        out["stat"].append({
            "size": size, "mtime_ns": ns, "mtime_repr": str(st.st_mtime),
            "etag": r.headers["etag"], "last_modified": r.headers["last-modified"],
        })

# 2. Range headers
many = ",".join(["0-0"] * 100)
HEADERS = [
    "bytes=0-", "bytes=0-0", "bytes=0-4", "bytes=5-", "bytes=-5", "bytes=-0", "bytes=-1000", "bytes=10-5", "bytes=0-9",
    "bytes=0-4,6-9", "bytes=0-4,3-9", "bytes=0-1,2-3,4-5", "bytes=9-9,0-0", "bytes=0-1,0-1", "bytes=4-5,0-9", " BYTES = 0-1",
    "bytes=0-1,", "bytes=,", "bytes=-", "bytes=", "bytes", "", "=0-1", "items=0-1", "Bytes=1-2", "bytes =1-2", "bytes\t=1-2",
    "bytes=a-b", "bytes=1-b", "bytes=a-1", "bytes=+1-+3", "bytes=1_0-2_0", "bytes=1__0-2", "bytes=_1-2", "bytes=1_-2",
    "bytes=0x1-2", "bytes=--3", "bytes=5--3", "bytes=1.5-2", "bytes= 1 - 2 ", "bytes=1-2-3", "bytes=0-4;q=1", "bytes=1-2,x,3-4",
    "bytes=0-99999999999999999999999", "bytes=99999999999999999999999-", "bytes=-99999999999999999999999",
    "bytes=-00005", "bytes=0000-0004", "bytes=3", "bytes=3,4", "bytes=0-4,\t5-9", "bytes=0-4\x1c,5-9", "bytes=\x1c0-4",
    "bytes=0-4,7", "bytes=0-4,-", "bytes=1-1,1-1,1-1", "bytes==0-1", "bytes=0-1=2", "bytes=0 -1", "bytes=0- 1",
    "bytes=" + many, "bytes=" + many + ",1-1", "bytes=" + ",".join(f"{i}-{i}" for i in range(0, 60, 2)),
    "bytes=0-1,2-3,4-5,6-7,8-9", "bytes=0-4,5-9", "bytes=0-4,6-9,5-5",
    "bytes=٣-٥", "bytes=0-٣", "bytes=0-1, 5-6", "bуtes=0-1", "bytes=0-１",
]
SIZES = [0, 1, 5, 10, 11, 100, 29430]
for h in HEADERS:
    for size in SIZES:
        try:
            res = {"ok": [list(p) for p in FileResponse._parse_range_header(h, size)]}
        except MalformedRangeHeader as exc:
            res = {"malformed": exc.content}
        except RangeNotSatisfiable as exc:
            res = {"unsat": exc.max_size}
        entry = {"header": h, "size": size, **res}
        if any(not c.isascii() and not c.isspace() for c in h):
            entry["declined"] = True  # the Rust port may refuse (Unsupported) instead of parsing Unicode digits
        out["range"].append(entry)

# 3. If-Range
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "f")
    open(path, "wb").write(b"abc")
    os.utime(path, ns=(1700000000_000000000,) * 2)
    r = FileResponse(path, stat_result=os.stat(path))
    lm, et = r.headers["last-modified"], r.headers["etag"]
    for v in [lm, et, "W/" + et, "W/" + lm, et[1:-1], "", lm.lower(), et + " ", " " + et, "*", "Mon, 09 Nov 2026 10:14:40 GMT"]:
        out["if_range"].append({"value": v, "last_modified": lm, "etag": et, "use": r._should_use_range(v)})

# 4. multipart
for ranges, size, ctype in [
    ([(0, 5), (7, 10)], 10, "text/html; charset=utf-8"), ([(0, 1), (2, 3), (4, 5)], 100, "application/javascript"),
    ([(0, 29430)], 29430, "application/javascript"), ([(9, 10), (0, 1)], 10, "text/html; charset=utf-8"),
    ([(10, 100), (1000, 10000)], 29430, "application/javascript"),
]:
    boundary = "0123456789abcdef0123456789"
    r = FileResponse.__new__(FileResponse)
    length, gen = FileResponse.generate_multipart(r, ranges, boundary, size, ctype)
    out["multipart"].append({
        "ranges": [list(p) for p in ranges], "size": size, "content_type": ctype, "boundary": boundary, "length": length,
        "headers": [gen(s, e).decode("latin-1") for s, e in ranges],
    })

print(json.dumps(out, ensure_ascii=False, indent=1))
