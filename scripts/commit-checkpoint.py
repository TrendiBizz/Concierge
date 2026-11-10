#!/usr/bin/env python3
"""Timer checkpoint: commit and push uncommitted work so nothing is lost.

This is NOT the session auto-end (that one gates on context pressure and runs
the full test/rust gates before pushing). This is the anti-data-loss net for
the window *between* commits, installed as a launchd LaunchAgent that runs
every 10 minutes:

    ~/Library/LaunchAgents/com.trendibizz.concierge-checkpoint.plist
    ~/Library/Logs/concierge-commit-checkpoint.log

Guardrails, each there because of a real failure mode in this repo:

- Never `push --force`, `reset --hard`, or `clean`. A rejected push keeps the
  commit local and exits non-zero for the log.
- `.gitignore` is respected, and the repo-local `Concierge` SSH key plus the
  known scratch paths are refused by name even if they stop being ignored.
- Untracked files are only added under code/doc prefixes and only up to
  MAX_UNTRACKED_BYTES. A stray credential or multi-GB artifact is skipped and
  logged, never committed.
- A merge/rebase in progress is never committed.
- A clean tree does nothing at all.

Usage:
    scripts/commit-checkpoint.py [--repo PATH] [--dry-run] [--message TEXT]
"""

from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys
from pathlib import Path

MAX_UNTRACKED_BYTES = 10 * 1024 * 1024

# Paths that must never be committed, even if .gitignore changes.
EXCLUDED_PREFIXES = (
    "QA/verification/HERMES_",
    "QA/verification/HANDOFF_HERMES_",
    "office-shots/",
    "tiktok-review/",
    ".private/",
)
EXCLUDED_EXACT = {".env", "Concierge"}
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")

# Untracked files may only enter under these prefixes (tracked edits are
# always allowed because they are already in the repository).
UNTRACKED_ALLOWED_PREFIXES = (
    "api/",
    "scripts/",
    "QA/",
    "concierge-stack/",
    "concierge-server/",
    "calendars/",
    "crm/",
    "payments/",
    "integrations/",
    "sites/",
    "vm/",
    "postgres/",
    "docs/",
    "tests/",
    "website/",
)
UNTRACKED_ALLOWED_FILES = {
    "AGENTS.md",
    "README.md",
    "HANDOFF.md",
    ".gitignore",
    "Caddyfile",
    "docker-compose.yml",
}

DEFAULT_LOG = Path.home() / "Library" / "Logs" / "concierge-commit-checkpoint.log"


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def log(message: str, logfile: Path) -> None:
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"{stamp} {message}"
    print(line)
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with logfile.open("a") as fh:
        fh.write(line + "\n")


def excluded(path: str) -> bool:
    if path in EXCLUDED_EXACT:
        return True
    if any(path.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return True
    if path.endswith(SENSITIVE_SUFFIXES):
        return True
    if path.startswith(".env."):
        return True
    return False


def untracked_allowed(path: str) -> bool:
    if path in UNTRACKED_ALLOWED_FILES:
        return True
    return any(path.startswith(prefix) for prefix in UNTRACKED_ALLOWED_PREFIXES)


def changed_entries(repo: Path) -> list[tuple[str, str, str | None]]:
    """Return (status, path, renamed_from) entries from `git status -z`."""
    out = run(["git", "status", "--porcelain", "-z", "--untracked-files=all"], repo).stdout
    fields = out.split("\0")
    entries: list[tuple[str, str, str | None]] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        if not entry:
            i += 1
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            old = fields[i + 1] if i + 1 < len(fields) else None
            entries.append((status, path, old))
            i += 2
        else:
            entries.append((status, path, None))
            i += 1
    return entries


def in_progress_operation(repo: Path) -> str | None:
    git_dir_out = run(["git", "rev-parse", "--git-dir"], repo)
    if git_dir_out.returncode != 0:
        return "not a git repository"
    git_dir = (repo / git_dir_out.stdout.strip()).resolve()
    for marker, label in (
        ("MERGE_HEAD", "merge"),
        ("rebase-merge", "rebase"),
        ("rebase-apply", "rebase"),
        ("CHERRY_PICK_HEAD", "cherry-pick"),
    ):
        if (git_dir / marker).exists():
            return label
    return None


def current_branch(repo: Path) -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--message")
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    logfile = Path(args.log).expanduser()

    operation = in_progress_operation(repo)
    if operation:
        log(f"SKIP repo={repo} reason={operation} in progress", logfile)
        return 0

    entries = changed_entries(repo)
    if not entries:
        log(f"clean repo={repo}", logfile)
        return 0

    stage: list[str] = []
    skipped: list[str] = []
    for status, path, _old in entries:
        if status.startswith("??"):
            if not untracked_allowed(path):
                skipped.append(f"{path} (untracked path not allowed)")
                continue
            full = repo / path
            try:
                size = full.stat().st_size
            except OSError:
                skipped.append(f"{path} (missing)")
                continue
            if size > MAX_UNTRACKED_BYTES:
                skipped.append(f"{path} ({size} bytes > limit)")
                continue
        if excluded(path):
            skipped.append(f"{path} (excluded)")
            continue
        stage.append(path)

    if not stage:
        log(f"SKIP repo={repo} nothing stageable; skipped={len(skipped)}", logfile)
        for item in skipped:
            log(f"  skipped {item}", logfile)
        return 0

    if args.dry_run:
        log(f"DRY-RUN repo={repo} would stage={stage} skipped={skipped}", logfile)
        return 0

    add = run(["git", "add", "--"] + stage, repo)
    if add.returncode != 0:
        log(f"FAIL git add: {(add.stderr or add.stdout).strip()}", logfile)
        return 2

    staged = [p for p in run(["git", "diff", "--cached", "--name-only"], repo).stdout.splitlines() if p.strip()]
    if not staged:
        log(f"SKIP repo={repo} nothing staged after add", logfile)
        return 0

    bad = [p for p in staged if excluded(p)]
    if bad:
        run(["git", "restore", "--staged", "--"] + bad, repo)
        for path in bad:
            log(f"REFUSED unstaged {path}", logfile)
        return 1

    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    message = args.message or f"checkpoint: automatic save {stamp}"

    commit = run(["git", "commit", "-m", message], repo)
    if commit.returncode != 0:
        log(f"FAIL git commit: {(commit.stdout + commit.stderr).strip()}", logfile)
        return 2
    sha = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()

    branch = current_branch(repo)
    if branch not in ("main", "master"):
        log(f"COMMITTED {sha[:7]} branch={branch} (not pushing non-main)", logfile)
        for item in skipped:
            log(f"  skipped {item}", logfile)
        return 0

    push = run(["git", "push", "origin", branch], repo)
    if push.returncode != 0:
        log(f"COMMITTED {sha[:7]} PUSH-REJECTED {(push.stderr or push.stdout).strip()}", logfile)
        return 1

    log(f"COMMITTED+PUSHED {sha[:7]} branch={branch} files={len(staged)}", logfile)
    for item in skipped:
        log(f"  skipped {item}", logfile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
