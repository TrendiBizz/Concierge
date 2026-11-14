"""Turn whatever the health check wrote into a subject and a body a human can act on.

Two defects made the 2026-11-15 alert hard to use:

1. `healthcheck.sh` piped the check's stderr into its stdout (`2>&1 | tee`), so the report file
   was not JSON whenever the check printed a note ("deploy grace: ...") — the mail then said
   "Failing checks: see payload" with the reason buried in raw text.
2. `alert.sh` looked for `checks` (a name -> bool map) that no report ever contained. The report
   has `failures` and `warnings`, each a list of {check, status, detail}, so the subject never
   named the failing check either.

This module is pure so both rules can be tested without SMTP.
"""
from __future__ import annotations

import json
import re

_OBJECT = re.compile(r"\{.*\}", re.S)


def parse_payload(payload: str) -> dict:
    """The report, even when something else was printed around it."""
    text = payload or ""
    for candidate in (text, (m.group(0) if (m := _OBJECT.search(text)) else "")):
        if not candidate.strip():
            continue
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {"raw": text[:4000]}


def failing(detail: dict) -> list[str]:
    """The names of what failed, however the report is shaped."""
    names: list[str] = []
    failures = detail.get("failures")
    if isinstance(failures, list):
        names += [str(f.get("check") or f.get("name") or "?") for f in failures if isinstance(f, dict)]
    checks = detail.get("checks")
    if isinstance(checks, dict):
        names += [str(name) for name, value in checks.items() if not value]
    elif isinstance(checks, list):
        names += [str(c.get("name", "?")) for c in checks if isinstance(c, dict) and not c.get("ok", True)]
    seen: set[str] = set()
    return [n for n in names if not (n in seen or seen.add(n))]


def summarise(payload: str) -> dict:
    """Subject suffix, failing names, and the body the mail should carry."""
    detail = parse_payload(payload)
    names = failing(detail)

    lines = ["Concierge health check failed on 152.42.239.240.", ""]
    counts = detail.get("counts")
    if isinstance(counts, dict):
        lines.append("Counts: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    for item in detail.get("failures") or []:
        if isinstance(item, dict):
            lines.append(f"FAIL {item.get('check', '?')}: {item.get('detail', '')}")
    for item in detail.get("warnings") or []:
        if isinstance(item, dict):
            lines.append(f"warn {item.get('check', '?')}: {item.get('detail', '')}")
    if not (detail.get("failures") or detail.get("warnings")) and "raw" in detail:
        lines.append("The report was not readable as JSON. Raw output follows.")
    lines += ["", json.dumps(detail, indent=2)[:6000]]
    return {
        "suffix": f" ({', '.join(names)})" if names else "",
        "failing": names,
        "body": "\n".join(lines) + "\n",
    }
