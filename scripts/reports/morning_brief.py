#!/usr/bin/env python3
"""Build the operator's morning report.

One report, three sources:
  * Omega live desk, read over SSH (service, mode, positions, closed trades).
  * Concierge, read from this repo + the deployed VPS.
  * Hermes lane reports, read from ~/.workwatch/reports/hermes.

The report is deterministic: every number carries its basis. If a source cannot be
read it is reported as UNANSWERED, never guessed.

Usage:
    python3 scripts/reports/morning_brief.py
    python3 scripts/reports/morning_brief.py --hours 24 --date 2026-11-18
    python3 scripts/reports/morning_brief.py --no-remote   # tests / offline
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPORT_DIR = Path.home() / ".workwatch" / "reports" / "hermes" / "trendi-master"
OMEGA_HOST = os.environ.get("OMEGA_HOST", "omega-new")
VPS_KEY = REPO / "Concierge"
VPS_HOST = "root@152.42.239.240"
LANES = ["seo-engine", "trendi-desk", "pen-test", "site-watch", "workwatch"]
# The harness can leak a half-written GIT_CONFIG_* block into child processes.
GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG_")}


def run(cmd: list[str], *, timeout: int = 60, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def ssh_omega(ps: str, *, timeout: int = 45) -> str:
    """Run one PowerShell command on the live Omega box."""
    result = run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
         "-o", "ControlMaster=no", "-o", "ControlPath=none", OMEGA_HOST,
         f'powershell -NoProfile -Command "{ps}"'],
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "ssh failed").strip()[:300])
    return result.stdout


def omega_status() -> dict:
    raw = ssh_omega(r"Get-Content C:\\Omega\\logs\\health\\status.json -Raw")
    data = json.loads(raw)
    checks = {c["name"]: c for c in data.get("checks", [])}
    mode = ""
    try:
        mode_lines = ssh_omega(r'findstr /i "mode" C:\\Omega\\omega_config.ini')
        for line in mode_lines.splitlines():
            if re.match(r"^\s*mode\s*=", line, re.I):
                mode = line.split("=", 1)[1].strip()
                break
    except Exception:
        mode = "UNKNOWN"

    watchdog = checks.get("protection.broker_watchdog", {}).get("detail", "")
    positions = re.search(r"(\d+)\s+broker position", watchdog)
    build = checks.get("binary.hash_matches_head", {}).get("detail", "")
    # IBKR order paths were closed on 2026-11-02 and IBKR was discontinued on
    # 2026-11-17. Its gateway check is a retired integration, not a desk fault.
    retired = {"ibkr.gateway": "IBKR retired 2026-11-17"}
    active = [c for c in data.get("checks", []) if c.get("name") not in retired]
    fail = [c for c in active if c.get("severity") == "FAIL"]
    warn = [c for c in active if c.get("severity") == "WARN"]
    overall = "FAIL" if fail else ("WARN" if warn else "OK")
    return {
        "overall": overall,
        "mode": mode or "UNKNOWN",
        "positions": int(positions.group(1)) if positions else None,
        "build": build,
        "checks": checks,
        "retired": retired,
        "fail": fail,
        "warn": warn,
    }


def omega_trades(hours: int, now: dt.datetime) -> list[dict]:
    raw = ssh_omega(r"Get-Content C:\\Omega\\logs\\trades\\omega_trade_closes.csv")
    rows = list(csv.DictReader(io.StringIO(raw)))
    cutoff = now - dt.timedelta(hours=hours)
    picked = []
    for row in rows:
        try:
            exited = dt.datetime.fromisoformat(row["exit_ts_utc"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if exited < cutoff:
            continue
        picked.append({
            "exit": exited,
            "symbol": row.get("symbol", ""),
            "engine": row.get("engine", ""),
            "side": row.get("side", ""),
            "entry": row.get("entry_px", ""),
            "exit_px": row.get("exit_px", ""),
            "net": float(row.get("net_pnl") or 0),
            "reason": row.get("exit_reason", ""),
            "shadow": row.get("shadow") == "1",
        })
    picked.sort(key=lambda r: r["exit"])
    return picked


def omega_last_live() -> dict | None:
    raw = ssh_omega(r"Get-Content C:\\Omega\\logs\\trades\\omega_trade_closes.csv")
    rows = list(csv.DictReader(io.StringIO(raw)))
    live = [r for r in rows if r.get("shadow") == "0"]
    if not live:
        return None
    row = max(live, key=lambda r: r.get("exit_ts_utc", ""))
    return {
        "exit": row.get("exit_ts_utc", ""),
        "symbol": row.get("symbol", ""),
        "engine": row.get("engine", ""),
        "net": float(row.get("net_pnl") or 0),
    }


def git_commits(hours: int, now: dt.datetime) -> list[dict]:
    since = (now - dt.timedelta(hours=hours)).astimezone().isoformat()
    result = run(
        ["git", "-C", str(REPO), "log", f"--since={since}",
         "--pretty=%h|%ad|%s", "--date=iso-strict"],
        env=GIT_ENV,
    )
    if result.returncode != 0:
        return []
    commits = []
    for line in result.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        sha, when, subject = parts
        if subject.startswith("checkpoint:"):
            continue
        commits.append({"sha": sha, "when": when, "subject": subject})
    return commits


def deploy_state() -> str:
    result = run(
        [str(REPO / "scripts/vps/verify-deploy.sh")],
        timeout=120,
        env={**os.environ, "KEY": str(VPS_KEY)},
    )
    text = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0 and "OK: repo and box agree" in text:
        return "repo and box agree"
    tail = [ln for ln in text.splitlines() if "DRIFT" in ln or "FAIL" in ln or "OK:" in ln]
    return "UNVERIFIED: " + ("; ".join(tail[-4:]) if tail else "verify-deploy failed")


def concierge_health() -> str:
    cmd = (
        "cd /opt/trendi/releases/20261108-vps/product && "
        "python3 scripts/vps/healthcheck.py --no-alert"
    )
    result = run(
        ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
         "-o", "ControlMaster=no", "-o", "ControlPath=none",
         "-i", str(VPS_KEY), VPS_HOST, cmd],
        timeout=120,
    )
    if result.returncode != 0:
        return "UNANSWERED (health check could not run)"
    try:
        data = json.loads(result.stdout)
        counts = data.get("counts", {})
        return f"{counts.get('ok', 0)} ok, {counts.get('warn', 0)} warn, {counts.get('fail', 0)} fail"
    except Exception:
        return "UNANSWERED (health output was not JSON)"


def lane_reports() -> list[dict]:
    out = []
    for lane in LANES:
        path = Path.home() / ".workwatch/reports/hermes" / lane / "latest.md"
        if not path.exists():
            out.append({"lane": lane, "status": "UNANSWERED (no report)", "head": "", "summary": ""})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        status = next((ln.split(":", 1)[1].strip()
                       for ln in text.splitlines() if ln.lower().startswith("status:")), "UNKNOWN")
        head = text.strip().splitlines()[0] if text.strip() else ""
        summary = ""
        for paragraph in re.split(r"\n\s*\n", text):
            paragraph = " ".join(paragraph.split())
            if not paragraph or paragraph.startswith("#") or paragraph.lower().startswith("status:"):
                continue
            summary = paragraph[:320]
            break
        out.append({
            "lane": lane, "status": status, "head": head,
            "summary": summary, "age": _age(path),
        })
    return out


def _age(path: Path) -> str:
    seconds = max(0, dt.datetime.now().timestamp() - path.stat().st_mtime)
    hours = seconds / 3600
    if hours < 1:
        return f"{int(seconds/60)}m old"
    if hours < 48:
        return f"{hours:.1f}h old"
    return f"{hours/24:.1f}d old"


def money(value: float) -> str:
    return f"{value:+.2f}"


def build_report(now: dt.datetime, hours: int, *, online: bool = True) -> str:
    omega_data = None
    omega_error = None
    last_live = None
    lines = [
        f"# Morning report — {now.strftime('%A %d %B %Y, %H:%M %Z')}",
        "",
        f"Window: last {hours} hours. Omega exits are timestamped in UTC; "
        "Concierge commits use the Mac clock. Every number below has its source in the line.",
        "",
    ]

    # ---- Omega -----------------------------------------------------------
    lines.append("## Omega")
    if not online:
        lines.append("UNANSWERED (remote checks disabled)")
    else:
        try:
            status = omega_status()
            omega_data = status
            trades = omega_trades(hours, now)
            last_live = omega_last_live()
            live = [t for t in trades if not t["shadow"]]
            shadow = [t for t in trades if t["shadow"]]
            live_net = sum(t["net"] for t in live)
            shadow_net = sum(t["net"] for t in shadow)
            state = "OK" if status["overall"] == "OK" else "ATTENTION"
            lines += [
                f"**Status: {state}.** Service reports `{status['overall']}`; "
                f"mode `{status['mode']}`; open broker positions `{status['positions']}`.",
                f"- Build: {status['build'] or 'UNKNOWN'}.",
                "- Retired check excluded: `ibkr.gateway` — IBKR was discontinued 2026-11-17.",
                f"- Trades in the last {hours}h: **{len(live)} live**, **{len(shadow)} shadow/paper**.",
                f"- Net closed P&L: live {money(live_net)}, shadow {money(shadow_net)}.",
            ]
            if last_live:
                lines.append(
                    f"- Last live trade on record: {last_live['exit']} "
                    f"{last_live['symbol']} {last_live['engine']} ({money(last_live['net'])})."
                )
            else:
                lines.append("- No live trade is on record.")
            if trades:
                lines.append("")
                lines.append("| Exit (UTC) | Book | Symbol | Engine | Side | Entry → exit | Net | Reason |")
                lines.append("|---|---|---|---|---|---|---:|---|")
                for t in trades:
                    book = "shadow" if t["shadow"] else "LIVE"
                    lines.append(
                        f"| {t['exit'].strftime('%d %b %H:%M')} | {book} | {t['symbol']} | "
                        f"{t['engine']} | {t['side']} | {t['entry']} → {t['exit_px']} | "
                        f"{money(t['net'])} | {t['reason']} |"
                    )
            else:
                lines.append(f"- No closed trades in the last {hours}h.")
            for check in status["fail"]:
                lines.append(f"- **FAIL** `{check['name']}`: {check.get('detail', '')}")
            for check in status["warn"]:
                lines.append(f"- WARN `{check['name']}`: {check.get('detail', '')}")
        except Exception as exc:  # noqa: BLE001 - the report must survive a source failure
            omega_error = str(exc)
            lines.append(f"UNANSWERED (Omega: {exc})")

    # ---- Concierge -------------------------------------------------------
    lines += ["", "## Concierge"]
    try:
        commits = git_commits(hours, now)
        head = run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], env=GIT_ENV).stdout.strip()
        if online:
            lines.append(f"- Deploy: **{deploy_state()}**; HEAD `{head}`.")
            lines.append(f"- Health: **{concierge_health()}**.")
        else:
            lines.append(f"- Deploy/health: UNANSWERED (remote checks disabled); HEAD `{head}`.")
        code = [c for c in commits if not re.match(r"^(handoff|docs|qa)\b", c["subject"], re.I)]
        docs = len(commits) - len(code)
        if code:
            groups: dict[str, int] = {}
            for c in code:
                area = re.split(r"[:\s]", c["subject"], maxsplit=1)[0].strip().lower()
                groups[area] = groups.get(area, 0) + 1
            areas = ", ".join(f"{k} ×{v}" for k, v in sorted(groups.items(), key=lambda kv: (-kv[1], kv[0]))[:8])
            lines.append(f"- Built or changed in the last {hours}h: {len(code)} code/config commits ({areas}).")
            lines.append("- Most recent:")
            for c in code[:6]:
                lines.append(f"  - `{c['sha']}` {c['subject']}")
        else:
            lines.append(f"- No code/config commits in the last {hours}h.")
        if docs:
            lines.append(f"- Handoffs/QA records updated: {docs} (not listed).")
        if not commits:
            lines.append(f"- No non-checkpoint commits in the last {hours}h.")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"UNANSWERED (Concierge: {exc})")

    # ---- Lanes -----------------------------------------------------------
    lines += ["", "## SEO engine and other lanes"]
    for lane in lane_reports():
        age = f" ({lane.get('age')})" if lane.get("age") else ""
        lines.append(f"- **{lane['lane']}**: {lane['status']}{age}.")
        if lane.get("summary"):
            lines.append(f"  {lane['summary']}")

    # ---- Needs Jo --------------------------------------------------------
    lines += ["", "## Needs you", ""]
    needs = []
    if omega_data:
        if omega_data["fail"]:
            needs.append(
                "Omega health is FAIL: " + "; ".join(
                    f"`{c['name']}` — {c.get('detail', '')}" for c in omega_data["fail"]
                ) + ". Decide whether to clear or accept each."
            )
        if omega_data["mode"].upper() == "SHADOW":
            when = last_live["exit"][:10] if last_live else "no live trade on record"
            needs.append(
                f"Omega is in SHADOW mode and the last live trade was {when}. "
                "Confirm that paper-only is intentional."
            )
    elif omega_error:
        needs.append(f"Omega could not be read: {omega_error}")
    for i, item in enumerate(needs, 1):
        lines.append(f"{i}. {item}")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--date", help="report date YYYY-MM-DD (default: today, local time)")
    parser.add_argument("--no-remote", action="store_true", help="skip Omega/VPS checks")
    parser.add_argument("--output", help="write here instead of the reports tree")
    args = parser.parse_args()

    now = dt.datetime.now().astimezone()
    if args.date:
        day = dt.date.fromisoformat(args.date)
        now = dt.datetime.combine(day, dt.time(8, 0), tzinfo=now.tzinfo)

    report = build_report(now, args.hours, online=not args.no_remote)
    if args.output:
        out = Path(args.output)
    else:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        out = REPORT_DIR / f"morning-{now.date().isoformat()}.md"
        (REPORT_DIR / "morning-latest.md").write_text(report, encoding="utf-8")
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[written] {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
