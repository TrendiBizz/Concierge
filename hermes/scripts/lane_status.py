#!/usr/bin/env python3
"""Print a deterministic lane-status table for the master brief.

Injected into the master's prompt by Hermes `--script`. It only reads the report
files; it never writes. A lane counts as answered only when there is a **dated routine
report** (`<profile>/<date>-<routine-id>.md`) younger than 36 hours. A bare
`latest.md` is not evidence: an agent can create one, and a placeholder must never be
mistaken for a real subagent run.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

REPORTS = Path(os.environ.get("HERMES_REPORTS", "/opt/data/.workwatch/reports/hermes"))
MAX_AGE_HOURS = 36

# Profiles and the routine ids that can produce a real report for them. Keep this in
# sync with schedules.yaml; test_manifest.py asserts it.
EXPECTED: dict[str, list[str]] = {
    "seo-engine": [
        "seo-daily-monitor",
        "seo-weekly-cycle",
        "seo-monthly-audit",
        "seo-innovation-scout",
    ],
    "trendi-desk": [
        "trendi-linkedin-weekly",
        "trendi-biweekly-news",
        "trendi-social-drafts",
        "trendi-deep-dive",
        "trendi-post-brief",
    ],
    "pen-test": [],
    "site-watch": ["trendi-tamper-watch"],
    "workwatch": ["workwatch-weekly-report"],
}

# Lanes whose only routine is deliberately paused in schedules.yaml. No report is
# expected, and the master must not read that as a failure.
PAUSED = {"site-watch"}


def status_of(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"(?m)^Status:\s*([A-Za-z][A-Za-z _-]*)", text)
    return match.group(1).strip() if match else None


def newest_real(profile: str) -> tuple[Path, float, str] | None:
    best: tuple[Path, float, str] | None = None
    for routine in EXPECTED.get(profile, []):
        for path in REPORTS.glob(f"{profile}/*-{routine}.md"):
            age = (time.time() - path.stat().st_mtime) / 3600
            if age > MAX_AGE_HOURS:
                continue
            if best is None or path.stat().st_mtime > best[1]:
                best = (path, age, routine)
    return best


def main() -> int:
    print(f"LANE STATUS TABLE (generated {datetime.now(timezone.utc).isoformat(timespec='seconds')})")
    print("profile | status | routine | file | age")
    answered = 0
    for profile in EXPECTED:
        real = newest_real(profile)
        if real:
            path, age, routine = real
            status = status_of(path) or "NO STATUS LINE"
            print(f"{profile} | {status} | {routine} | {path.name} | {age:.1f}h")
            answered += 1
        elif profile in PAUSED:
            routine = (EXPECTED[profile] or ["-"])[0]
            print(f"{profile} | PAUSED | {routine} | - | -")
        elif not EXPECTED[profile]:
            print(f"{profile} | NO ROUTINE | - | - | -")
        else:
            placeholder = (REPORTS / profile / "latest.md").exists()
            note = "placeholder latest.md ignored" if placeholder else "-"
            print(f"{profile} | NO REPORT | - | {note} | -")
    print(f"ANSWERED: {answered}/{len(EXPECTED)}")
    print(
        "A lane is UNANSWERED unless this table gives a status from a dated routine report. "
        "Do not create a lane report yourself; a placeholder is a fabrication."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
