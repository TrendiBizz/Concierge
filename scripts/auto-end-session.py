#!/usr/bin/env python3
"""Auto-end a session at context threshold, then commit, gate, and push.

Owner decision 2026-11-10: trigger on context size; push automatically to
origin/main. See QA/verification/SPEC_SESSION_AUTOEND_AUTOPUSH_2026-11-10.md.

Trigger input is the token meter's CONTEXT PRESSURE (pressureTokens /
contextWindow) -- never the lifetime tokenUsage total. Those two appear side by
side in the Web status bar (e.g. "11.3M tok . 29%"); the lifetime figure counts
the whole conversation again every turn and can never be compared to the window.

Usage:
    auto-end-session.py --pressure 0.83 --window 1048576 --tokens 870000
    auto-end-session.py --from-statusbar "11.3M tok . 29%"
    auto-end-session.py --dry-run --pressure 0.83 --window 1048576

Exit codes:
    0  ended (commit+push done, or nothing to do)
    1  refused (red gate, unknown staged paths, rejected push) -- nothing pushed
    2  bad input
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Default fraction of the window. Matches compaction-basic's thresholdRatio so
# the two agree on when pressure has meaningfully built.
DEFAULT_THRESHOLD = 0.80

# Paths that must never be committed. These are known-untracked scratch output;
# the handoff records repeated instructions not to commit them.
EXCLUDED_PREFIXES = (
    "QA/verification/HERMES_",
    "office-shots/",
    "tiktok-review/",
)

# Anything staged outside this set is a surprise and must stop the push.
ALLOWED_STAGED_PREFIXES = (
    "QA/verification/",
    "api/",
    "scripts/",
    "concierge-server/",
    "calendars/",
    "crm/",
    "payments/",
    "integrations/",
    "sites/",
    "vm/",
    "postgres/",
    "concierge-stack/",
    ".github/",
)

ALLOWED_STAGED_FILES = {
    "AGENTS.md",
    "README.md",
    "HANDOFF.md",
    "Caddyfile",
    "docker-compose.yml",
    "docker-compose.twenty-bridge.yml",
    ".gitignore",
    ".env.example",
}

GATE_TESTS = ["pytest", "api/tests", "-q"]


class Refused(Exception):
    """A guardrail stopped the sequence. Nothing was pushed."""


def run(args: list[str], *, cwd: Path, env_pytest: bool = False) -> subprocess.CompletedProcess:
    environ = None
    if env_pytest:
        import os

        environ = {**os.environ, "PYTHONPATH": "api"}
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, env=environ, check=False
    )


def parse_statusbar(text: str) -> tuple[float, int]:
    """Parse the Web status bar into (lifetime_tokens, occupancy_fraction).

    The bar shows a lifetime total and a live percentage. Only the percentage is
    a fraction of the window; the token figure is NOT occupancy.
    """
    m = re.search(r"([\d.]+)\s*([KMB]?)\s*tok", text, re.IGNORECASE)
    if not m:
        raise ValueError(f"no '<n> tok' figure in {text!r}")
    value = float(m.group(1))
    mult = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[m.group(2).upper()]
    lifetime = int(value * mult)

    p = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if not p:
        raise ValueError(f"no percentage in {text!r}")
    return lifetime, float(p.group(1)) / 100.0


def occupancy(pressure_tokens: int, window: int) -> float:
    if window <= 0:
        raise ValueError("window must be positive")
    return pressure_tokens / window


def should_end(fraction: float, threshold: float) -> bool:
    return fraction >= threshold


def excluded(path: str) -> bool:
    return any(path.startswith(p) for p in EXCLUDED_PREFIXES)


def staged_paths(repo: Path) -> list[str]:
    out = run(["git", "diff", "--cached", "--name-only"], cwd=repo)
    return [line for line in out.stdout.splitlines() if line.strip()]


def unstaged_untracked(repo: Path) -> list[str]:
    out = run(["git", "status", "--porcelain"], cwd=repo)
    paths = []
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:  # rename
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip('"'))
    return paths


def check_staged_are_expected(repo: Path) -> None:
    """Refuse when something unexpected is staged.

    This is the guardrail that stops a stray credential or multi-GB artifact
    from reaching origin/main unattended.
    """
    for path in staged_paths(repo):
        if excluded(path):
            raise Refused(f"excluded path is staged: {path}")
        if path in ALLOWED_STAGED_FILES:
            continue
        if not any(path.startswith(p) for p in ALLOWED_STAGED_PREFIXES):
            raise Refused(f"unexpected staged path (not in allowlist): {path}")


def run_gates(repo: Path) -> None:
    """The Python suite must pass; a red test gate blocks the push.

    The Rust gate was removed on 2026-11-10 when the Rust port was abandoned;
    `concierge-stack/` is reference only and is not part of the product.
    """
    # Rust port abandoned 2026-11-10: only the Python suite gates a push.
    tests = run(GATE_TESTS, cwd=repo, env_pytest=True)
    if tests.returncode != 0:
        tail = (tests.stdout or tests.stderr).strip().splitlines()[-15:]
        raise Refused("pytest gate FAILED:\n" + "\n".join(tail))


def current_branch(repo: Path) -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip()


def commit_and_push(repo: Path, message: str, *, dry_run: bool) -> dict:
    check_staged_are_expected(repo)

    if not staged_paths(repo):
        return {"committed": False, "pushed": False, "reason": "nothing staged"}

    run_gates(repo)

    if dry_run:
        return {
            "committed": False,
            "pushed": False,
            "reason": "dry-run",
            "would_commit": staged_paths(repo),
        }

    commit = run(["git", "commit", "-m", message], cwd=repo)
    if commit.returncode != 0:
        raise Refused("commit failed:\n" + (commit.stdout + commit.stderr).strip())

    sha = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    branch = current_branch(repo)

    push = run(["git", "push", "origin", branch], cwd=repo)
    if push.returncode != 0:
        # Never force. A rejection means origin moved; that is the owner's call.
        raise Refused(
            "push REJECTED -- stopping without force.\n"
            + (push.stderr or push.stdout).strip()
        )

    return {"committed": True, "pushed": True, "sha": sha, "branch": branch}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="repository root (default: cwd)")
    ap.add_argument("--pressure", type=int, help="current prompt-side pressure tokens")
    ap.add_argument("--window", type=int, help="routed model context window")
    ap.add_argument("--tokens", type=int, help="alias for --pressure")
    ap.add_argument("--from-statusbar", help="parse '11.3M tok . 29%%' (uses only the %%)")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--message", help="commit message; default names the trigger")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    result: dict = {"repo": str(repo)}

    try:
        # --- resolve occupancy ------------------------------------------------
        if args.from_statusbar:
            lifetime, fraction = parse_statusbar(args.from_statusbar)
            result["lifetime_tokens_ignored"] = lifetime
            result["occupancy"] = round(fraction, 4)
        else:
            pressure = args.pressure if args.pressure is not None else args.tokens
            if pressure is None or args.window is None:
                print("error: need --pressure/--tokens and --window, or --from-statusbar", file=sys.stderr)
                return 2
            fraction = occupancy(pressure, args.window)
            result["pressure_tokens"] = pressure
            result["context_window"] = args.window
            result["occupancy"] = round(fraction, 4)

        result["threshold"] = args.threshold

        # --- trigger ----------------------------------------------------------
        if not should_end(fraction, args.threshold):
            result.update(ended=False, reason="below threshold")
            emit(result, args.json)
            return 0

        message = args.message or (
            f"Auto-end at {fraction:.0%} context pressure (threshold {args.threshold:.0%})"
        )
        outcome = commit_and_push(repo, message, dry_run=args.dry_run)
        result.update(ended=True, **outcome)
        emit(result, args.json)
        return 0

    except Refused as exc:
        result.update(ended=False, refused=True, reason=str(exc))
        emit(result, args.json)
        return 1
    except (ValueError, OSError) as exc:
        result.update(ended=False, error=str(exc))
        emit(result, args.json)
        return 2


def emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
        return
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    sys.exit(main())
