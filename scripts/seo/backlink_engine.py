#!/usr/bin/env python3
"""Backlink pipeline: shortlist, report, and verify claimed links.

Data lives beside this script:
  prospects.csv  every target, its asset, status and next action
  outreach.csv   every send and reply
  links.csv      every claimed link; a link is not "won" until verified

Usage:
  python3 scripts/seo/backlink_engine.py queue [--limit 10]
  python3 scripts/seo/backlink_engine.py report
  python3 scripts/seo/backlink_engine.py verify [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent / "backlinks"
PROSPECTS = HERE / "prospects.csv"
OUTREACH = HERE / "outreach.csv"
LINKS = HERE / "links.csv"
UA = "TrendiLinkCheck/1.0 (+https://trendibizz.com)"
ACTIVE = {"prospect", "researching", "ready", "pitched", "follow-up"}


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def queue(limit: int = 10) -> list[dict]:
    items = [r for r in rows(PROSPECTS) if (r.get("status") or "").lower() in ACTIVE]
    items.sort(key=lambda r: (int(r.get("tier") or 9), int(r.get("priority") or 9), int(r.get("id") or 999)))
    return items[:limit]


def counts_by(field: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows(PROSPECTS):
        key = (r.get(field) or "unknown").strip() or "unknown"
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def link_state() -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows(LINKS):
        key = (r.get("status") or "unverified").strip() or "unverified"
        out[key] = out.get(key, 0) + 1
    return out


def fmt_queue(items: list[dict]) -> str:
    lines = [f"{'ID':>3}  {'T':<2} {'P':<2} {'STATUS':<11} {'ASSET':<20} DOMAIN", "-" * 78]
    for r in items:
        lines.append(
            f"{r.get('id',''):>3}  {r.get('tier',''):<2} {r.get('priority',''):<2} "
            f"{(r.get('status') or ''):<11} {(r.get('asset') or ''):<20} {r.get('domain','')}"
        )
        if r.get("next_action"):
            lines.append(f"       next: {r['next_action']}")
    return "\n".join(lines)


def report() -> str:
    prospects = rows(PROSPECTS)
    sends = rows(OUTREACH)
    links = rows(LINKS)
    live = [r for r in links if (r.get("status") or "").lower() == "live"]
    lost = [r for r in links if (r.get("status") or "").lower() == "lost"]
    due = [r for r in sends if (r.get("next_followup") or "") and r["next_followup"] <= str(dt.date.today())
           and (r.get("status") or "").lower() not in {"replied", "won", "declined", "closed"}]
    lines = [
        f"# Backlink pipeline — {dt.date.today().isoformat()}",
        "",
        f"- Prospects: **{len(prospects)}** total; active **{sum(1 for r in prospects if (r.get('status') or '') in ACTIVE)}**.",
        f"- Outreach rows: **{len(sends)}**; due follow-ups: **{len(due)}**.",
        f"- Claimed links: **{len(links)}**; live **{len(live)}**; lost **{len(lost)}**.",
        "",
        "## By tier",
    ]
    for tier, n in counts_by("tier").items():
        lines.append(f"- Tier {tier}: {n}")
    lines += ["", "## By status"]
    for status, n in counts_by("status").items():
        lines.append(f"- {status}: {n}")
    lines += ["", "## By asset"]
    for asset, n in counts_by("asset").items():
        lines.append(f"- {asset}: {n}")
    if due:
        lines += ["", "## Follow-ups due"]
        for r in due:
            lines.append(f"- {r.get('prospect_id')} via {r.get('channel')}: {r.get('subject')} (due {r.get('next_followup')})")
    lines += ["", "## This week's shortlist"]
    lines.append(fmt_queue(queue(10)))
    return "\n".join(lines).rstrip() + "\n"


def verify_link(row: dict, *, timeout: int = 20) -> tuple[str, str]:
    """Return (status, note). A link is live only if the source returns 200 and names the target."""
    source = (row.get("source_url") or "").strip()
    target = (row.get("target_url") or "").strip()
    if not source or not target:
        return "unverified", "missing source or target URL"
    try:
        req = urllib.request.Request(source, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return "lost", f"HTTP {resp.status}"
            body = resp.read(500_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return "lost", f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return "unverified", f"fetch failed: {type(exc).__name__}"
    host = urllib.parse.urlparse(target).netloc.removeprefix("www.")
    if target in body or (host and host in body):
        return "live", "found target in source HTML"
    return "lost", "source is 200 but target not found"


def verify(*, dry_run: bool = False) -> int:
    links = rows(LINKS)
    if not links:
        print("No links to verify yet.")
        return 0
    changed = 0
    for row in links:
        status, note = verify_link(row)
        row["status"] = status
        row["last_checked"] = dt.date.today().isoformat()
        row["notes"] = (row.get("notes") or "").strip()
        if note and note not in row["notes"]:
            row["notes"] = (row["notes"] + "; " if row["notes"] else "") + note
        print(f"{row.get('id','?'):>3} {status:<10} {row.get('source_url','')} — {note}")
        changed += 1
    if not dry_run and changed:
        fields = ["id", "source_url", "target_url", "anchor", "rel", "first_seen", "last_checked", "status", "notes"]
        with LINKS.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(links)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("queue")
    q.add_argument("--limit", type=int, default=10)
    sub.add_parser("report")
    v = sub.add_parser("verify")
    v.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.cmd == "queue":
        print(fmt_queue(queue(args.limit)))
    elif args.cmd == "report":
        print(report())
    elif args.cmd == "verify":
        return verify(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
