"""Batch-25 golden vectors: the client report page of `main.py` (`_money`, the SVG bar arithmetic and every
`html.escape` call inside `client_report`), read from the live module with fake inputs. No server, no database.

The point of these vectors is the *rendering* rules: `{:.1f}`, `%b %d`, `str.title()` and `html.escape` at the
exact call sites `client_report` uses. The aggregation SQL is proven separately by the differential harness
(`QA/verification/rust_server_parity.py`), which runs both servers over one real PostgreSQL.

    cd api && python ../concierge-stack/core-rs/parity/gen_vectors25.py > ../concierge-stack/core-rs/parity/vectors25.json
"""
import html
import json
import sys

sys.path.insert(0, ".")
from app.main import _money  # noqa: E402

out = {"escape": [], "money": [], "title": [], "month_day": [], "bars": [], "clamp": []}

# 1. html.escape at the call sites client_report uses, including the characters that appear in tenant names,
#    lead names, messages, channels, statuses and score labels.
escape_inputs = [
    "Open Co", "Ünï & Co", "Ann & <b>Bob</b>", 'Wants a "quote" & <script>alert(1)</script>', "it's",
    "<", ">", "&", '"', "'", "&amp;", "&#39;", "", "plain text", "é中", "x\x00y", "a\nb", "#ff00aa",
    "</td><script>", "½¼¾", "İstanbul", "ﬁ ligature", "𝔘𝔫𝔦𝔠𝔬𝔡𝔢", "tab\there",
]
for s in escape_inputs:
    out["escape"].append({"in": s, "out": html.escape(s)})

# 2. _money, including the negative and rounding branches.
for cents in [0, 1, 50, 99, 100, 150, 2500, 15000, 123456789, -1, -100, -2500, -50, 10**15]:
    out["money"].append({"cents": cents, "out": _money(cents)})

# 3. str.title() on the score labels the table renders.
for s in ["cold", "warm", "hot", "COLD", "hot lead", "", "a-b", "o'brien", "élan", "3rd party", "x  y", "ünï"]:
    out["title"].append({"in": s, "out": s.title()})

# 4. strftime("%b %d") as used on r['created_at'].
import datetime  # noqa: E402

for dt in [
    datetime.datetime(2026, 1, 1), datetime.datetime(2026, 1, 9), datetime.datetime(2026, 11, 9),
    datetime.datetime(2026, 12, 31), datetime.datetime(2024, 2, 29), datetime.datetime(2026, 7, 5),
]:
    out["month_day"].append({"iso": dt.isoformat(), "out": dt.strftime("%b %d")})

# 5. The exact bar arithmetic from client_report, for the shapes the seeded data produces: an empty daily
#    list, a single day, a flat series, and a series with a zero day next to large ones.
def bars_for(daily, accent):
    peak = max([d["leads"] for d in daily] + [d["conversations"] for d in daily] + [1])
    bar_w = 600 / max(len(daily), 1)
    out_bars = []
    for i, d in enumerate(daily):
        x = i * bar_w
        h_c = 100 * d["conversations"] / peak
        h_l = 100 * d["leads"] / peak
        out_bars.append(
            f'<rect x="{x:.1f}" y="{110 - h_c:.1f}" width="{max(bar_w * 0.4, 1):.1f}" height="{h_c:.1f}" fill="#94a3b8"/>'
            f'<rect x="{x + bar_w * 0.45:.1f}" y="{110 - h_l:.1f}" width="{max(bar_w * 0.4, 1):.1f}" height="{h_l:.1f}" fill="{html.escape(accent)}"/>'
        )
    return "".join(out_bars)


series = [
    ([], "#2563eb"),
    ([{"conversations": 0, "leads": 0}], "#2563eb"),
    ([{"conversations": 3, "leads": 1}] * 30, "#ff00aa"),
    ([{"conversations": 0, "leads": 5}, {"conversations": 9, "leads": 0}, {"conversations": 2, "leads": 2}], "#00ff00"),
    ([{"conversations": 1, "leads": 1}] * 7, "Ünï & Co"),
    ([{"conversations": 7, "leads": 3}] * 366, "#123456"),
    ([{"conversations": 1, "leads": 100}, {"conversations": 99, "leads": 1}], "#abcdef"),
]
for daily, accent in series:
    out["bars"].append({"daily": daily, "accent": accent, "out": bars_for(daily, accent)})

# 6. days = min(max(days, 1), 365), as _stats applies it.
def clamp(d):
    return min(max(d, 1), 365)


for d in [-10**24, -1, 0, 1, 7, 30, 365, 366, 10**6, 10**24, -(2**63), 2**63]:
    out["clamp"].append({"in": str(d), "out": clamp(d)})

print(json.dumps(out, ensure_ascii=False, indent=1))
