#!/usr/bin/env python3
"""Install the Hermes master, subagent profiles and cron jobs.

Reads schedules.yaml, creates one Hermes profile per entry, writes each profile's
SOUL.md, and registers one cron job per routine. Idempotent: a job whose desired
schedule/prompt/status hash matches the recorded state is left alone; anything else is
replaced. Run with --dry-run first.

    python3 install.py --dry-run
    python3 install.py --apply
    python3 install.py --apply --only seo-daily-monitor,trendi-social-drafts
    python3 install.py --apply --force          # replace every job

Inside the Mac container:
    docker exec hermes-concierge python3 /opt/data/work/hermes/install.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - the container and the test venv both have it
    sys.exit("PyYAML is required (pip install pyyaml)")

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "schedules.yaml"
DEFAULT_HOME = "/opt/data"

# Each Hermes profile gets its own HOME. The Trendi scripts use Path.home() as well as
# the absolute /Users/jo paths, so link the profile home at the mounted data. A link,
# not a copy: the keys stay read-only in the mount and are never duplicated.
PROFILE_LINKS = {
    ".config/trendi": ".config/trendi",
    ".config/trendi-seo": ".config/trendi-seo",
    ".workwatch": ".workwatch",
    "OpenBot": "OpenBot",
    "jo-brain": "jo-brain",
}


# --------------------------------------------------------------------------- manifest
def load_manifest(path: Path | str = MANIFEST_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "profiles" not in data or "routines" not in data:
        raise ValueError(f"{path}: expected profiles and routines")
    return data


def hermes_home(explicit: str | None = None) -> Path:
    return Path(explicit or os.environ.get("HERMES_HOME") or DEFAULT_HOME)


def hermes_binary(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    found = shutil.which("hermes")
    if not found:
        raise SystemExit("hermes is not on PATH; pass --hermes /path/to/hermes")
    return found


def profile_dir(home: Path, profile: str) -> Path:
    return home if profile == "default" else home / "profiles" / profile


def jobs_file(home: Path, profile: str) -> Path:
    return profile_dir(home, profile) / "cron" / "jobs.json"


def read_jobs(home: Path, profile: str) -> list[dict[str, Any]]:
    path = jobs_file(home, profile)
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("jobs", []))
    except (json.JSONDecodeError, OSError):
        return []


def find_job(home: Path, profile: str, name: str) -> dict[str, Any] | None:
    for job in read_jobs(home, profile):
        if job.get("name") == name:
            return job
    return None


# ------------------------------------------------------------------------------ prompt
def build_prompt(manifest: dict[str, Any], routine: dict[str, Any], procedure: str) -> str:
    reports = manifest.get("reports_dir", "~/.workwatch/reports/hermes")
    return (
        f"You are running the Hermes routine `{routine['id']}` "
        f"on the `{routine['profile']}` profile.\n\n"
        f"Workdir: {routine.get('workdir', manifest.get('workdir', '/opt/data/work/hermes'))}\n"
        f"Reports: {reports}/{routine['profile']}/\n\n"
        "Follow the procedure below exactly. The standing policy in AGENTS.md is "
        "binding and overrides the procedure if they differ. Do not send, post, deploy "
        "or spend. Write the report before you finish.\n\n"
        "Required report completion (also on quiet/blocked runs):\n"
        "Compute YYYY-MM-DD at execution time with Python datetime.now(\n"
        "    ZoneInfo('Pacific/Auckland')).date().isoformat()\n"
        "(from datetime import datetime; from zoneinfo import ZoneInfo).\n"
        f"Create {reports}/{routine['profile']}/ if missing. Use write_file or a "
        "terminal file write to save the actual report to\n"
        f"{reports}/{routine['profile']}/<YYYY-MM-DD>-{routine['id']}.md\n"
        f"with '# {routine['id']} — <YYYY-MM-DD>' and an unbolded Status: line.\n"
        f"Copy identical content to {reports}/{routine['profile']}/latest.md, then "
        "read back both files with a file tool and verify content matches.\n"
        "Only then finish or return [SILENT]. A response claiming a save is not a "
        "file write. If writing/verification fails, return [CRON_FAILURE] on the "
        "first line followed by WRITE FAILED, the path and error.\n\n"
        "---\n\n"
        f"{procedure.strip()}\n"
    )


def desired_hash(manifest: dict[str, Any], routine: dict[str, Any], prompt: str) -> str:
    payload = {
        "prompt": prompt,
        "schedule": routine["schedule"],
        "enabled": bool(routine.get("enabled", True)),
        "timezone": routine.get("timezone", manifest["timezone"]),
        "workdir": routine.get("workdir", manifest.get("workdir")),
        "catch_up": bool(routine.get("catch_up", True)),
        "continuity": bool(routine.get("continuity", False)),
        "paused_reason": routine.get("paused_reason"),
        "script": routine.get("script"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def state_path(manifest: dict[str, Any], explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    return Path(manifest.get("reports_dir", "~/.workwatch/reports/hermes")) / "install-state.json"


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


# ------------------------------------------------------------------------------- plan
def plan(
    manifest: dict[str, Any],
    home: Path,
    *,
    only: set[str] | None = None,
    force: bool = False,
    state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    state = state or {}
    actions: list[dict[str, Any]] = []

    for name, spec in manifest["profiles"].items():
        pdir = profile_dir(home, name)
        actions.append(
            {
                "kind": "profile",
                "name": name,
                "exists": pdir.exists(),
                "description": spec.get("description", ""),
            }
        )
        soul = ROOT / spec["soul"]
        actions.append(
            {
                "kind": "soul",
                "name": name,
                "path": pdir / "SOUL.md",
                "source": soul,
                "exists": (pdir / "SOUL.md").exists(),
            }
        )
        actions.append({"kind": "links", "name": name, "profile": name})

    for routine in manifest["routines"]:
        if only and routine["id"] not in only:
            continue
        procedure_path = ROOT / routine["procedure"]
        procedure = procedure_path.read_text(encoding="utf-8")
        prompt = build_prompt(manifest, routine, procedure)
        digest = desired_hash(manifest, routine, prompt)
        existing = find_job(home, routine["profile"], routine["id"])
        recorded = (state.get(routine["id"]) or {}).get("hash")
        if existing is None:
            action = "create"
        elif force or recorded != digest:
            action = "replace"
        else:
            action = "skip"
        if routine.get("script"):
            script_src = ROOT / routine["script"]
            actions.append(
                {
                    "kind": "script",
                    "name": f"{routine['profile']}/{script_src.name}",
                    "profile": routine["profile"],
                    "source": script_src,
                    "target": profile_dir(home, routine["profile"]) / "scripts" / script_src.name,
                }
            )
        actions.append(
            {
                "kind": "job",
                "name": routine["id"],
                "profile": routine["profile"],
                "action": action,
                "existing_id": (existing or {}).get("id"),
                "schedule": routine["schedule"],
                "enabled": bool(routine.get("enabled", True)),
                "hash": digest,
                "prompt": prompt,
                "routine": routine,
            }
        )
    return actions


# ------------------------------------------------------------------------------- apply
def run(cmd: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=False,
        text=True,
        capture_output=capture,
        env={**os.environ, "HERMES_ACCEPT_HOOKS": "1"},
    )


def create_profile(hermes: str, name: str, description: str, home: Path) -> None:
    cmd = [
        hermes,
        "profile",
        "create",
        name,
        "--clone",
        "--no-alias",
        "--description",
        description,
    ]
    result = run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"profile create {name} failed: {result.stderr.strip()}")
    # --clone should carry .env; if the default has a key and the clone did not, copy it.
    src = home / ".env"
    dst = profile_dir(home, name) / ".env"
    if src.exists() and not dst.exists():
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        dst.chmod(0o600)


def write_soul(home: Path, name: str, source: Path) -> None:
    target = profile_dir(home, name) / "SOUL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    target.chmod(0o644)


def ensure_profile_links(home: Path, profile: str) -> None:
    """Link a profile's HOME at the mounted data, so Path.home() sees the keys and repos."""
    profile_home = profile_dir(home, profile) / "home"
    profile_home.mkdir(parents=True, exist_ok=True)
    for rel, target_rel in PROFILE_LINKS.items():
        target = home / target_rel
        link = profile_home / rel
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            if os.readlink(link) == str(target):
                continue
            link.unlink()
        elif link.exists():
            # A real directory (an older agent may have copied keys here). Do not delete
            # it silently; report it so a human can decide.
            print(f"  ! {link} exists and is not a symlink; left in place")
            continue
        link.symlink_to(target, target_is_directory=True)


def remove_job(hermes: str, profile: str, job_id: str) -> None:
    result = run([hermes, "-p", profile, "cron", "remove", job_id])
    if result.returncode != 0:
        # A vanished job is fine; a real failure is reported by the caller's next step.
        print(f"  ! could not remove {job_id} on {profile}: {result.stderr.strip()}")


def create_job(
    hermes: str, manifest: dict[str, Any], routine: dict[str, Any], prompt: str
) -> str:
    profile = routine["profile"]
    cmd = [
        hermes,
        "-p",
        profile,
        "cron",
        "create",
        "--name",
        routine["id"],
        "--timezone",
        routine.get("timezone", manifest["timezone"]),
        "--deliver",
        routine.get("deliver", "local"),
        "--catch-up",
        "on" if routine.get("catch_up", True) else "off",
    ]
    if routine.get("continuity"):
        cmd.append("--continuity")
    if routine.get("script"):
        cmd += ["--script", Path(routine["script"]).name]
    workdir = routine.get("workdir", manifest.get("workdir"))
    if workdir:
        cmd += ["--workdir", workdir]
    if routine.get("model"):
        cmd += ["--model", routine["model"]]
    if routine.get("enabled", True):
        pass
    else:
        cmd += ["--paused"]
        reason = routine.get("paused_reason") or "paused by schedules.yaml"
        cmd += ["--paused-reason", reason]
    cmd += ["--", routine["schedule"], prompt]
    result = run(cmd)
    if result.returncode != 0:
        raise RuntimeError(
            f"cron create {routine['id']} on {profile} failed: {result.stderr.strip()}"
        )
    match = re.search(r"Created job:\s*([0-9a-f]+)", result.stdout)
    if not match:
        raise RuntimeError(
            f"cron create {routine['id']} returned no job id: {result.stdout.strip()}"
        )
    return match.group(1)


def apply_plan(
    actions: list[dict[str, Any]],
    manifest: dict[str, Any],
    home: Path,
    hermes: str,
    state_file: Path,
    state: dict[str, Any],
) -> tuple[int, int]:
    created_profiles = 0
    created_jobs = 0
    for action in actions:
        if action["kind"] == "profile" and not action["exists"]:
            print(f"PROFILE {action['name']}: create")
            create_profile(hermes, action["name"], action["description"], home)
            created_profiles += 1
        elif action["kind"] == "soul":
            write_soul(home, action["name"], action["source"])
            print(f"SOUL    {action['name']}: written")
        elif action["kind"] == "links":
            ensure_profile_links(home, action["profile"])
            print(f"LINKS   {action['profile']}: ensured")
        elif action["kind"] == "script":
            target = action["target"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(action["source"], target)
            target.chmod(0o755)
            print(f"SCRIPT  {action['name']}: copied")
        elif action["kind"] == "job":
            if action["action"] == "skip":
                print(f"JOB     {action['name']}: unchanged")
                continue
            if action["action"] == "replace" and action["existing_id"]:
                remove_job(hermes, action["profile"], action["existing_id"])
            job_id = create_job(hermes, manifest, action["routine"], action["prompt"])
            state[action["name"]] = {
                "profile": action["profile"],
                "job_id": job_id,
                "hash": action["hash"],
                "schedule": action["schedule"],
                "enabled": action["enabled"],
            }
            print(
                f"JOB     {action['name']}: {action['action']} -> {job_id}"
                f" ({action['profile']}, {action['schedule']}, "
                f"{'enabled' if action['enabled'] else 'paused'})"
            )
            created_jobs += 1
    state["_updated"] = "install.py"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return created_profiles, created_jobs


# -------------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="make the changes (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    parser.add_argument("--force", action="store_true", help="replace every job")
    parser.add_argument("--only", default="", help="comma-separated routine ids")
    parser.add_argument("--profiles-only", action="store_true", help="create profiles and SOULs only")
    parser.add_argument("--home", default=None, help="Hermes home (default /opt/data)")
    parser.add_argument("--hermes", default=None, help="path to the hermes binary")
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument("--state", default=None, help="install-state.json path")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    home = hermes_home(args.home)
    only = {part.strip() for part in args.only.split(",") if part.strip()} or None
    state_file = state_path(manifest, args.state)
    state = load_state(state_file)

    actions = plan(manifest, home, only=only, force=args.force, state=state)
    jobs = [a for a in actions if a["kind"] == "job"]
    if args.profiles_only:
        jobs = []
        actions = [a for a in actions if a["kind"] != "job"]

    print(f"Hermes home: {home}")
    print(f"Manifest:    {args.manifest}")
    print(f"State:       {state_file}")
    apply = args.apply and not args.dry_run
    print(f"Mode:        {'APPLY' if apply else 'DRY RUN'}")
    print()

    if not apply:
        for action in actions:
            if action["kind"] == "profile":
                print(f"PROFILE {action['name']}: {'exists' if action['exists'] else 'create'}")
            elif action["kind"] == "soul":
                print(f"SOUL    {action['name']}: {'overwrite' if action['exists'] else 'write'}")
            elif action["kind"] == "links":
                print(f"LINKS   {action['name']}: ensure")
            elif action["kind"] == "script":
                print(f"SCRIPT  {action['name']}: copy")
            elif action["kind"] == "job":
                print(
                    f"JOB     {action['name']}: {action['action']} "
                    f"({action['profile']}, {action['schedule']}, "
                    f"{'enabled' if action['enabled'] else 'paused'})"
                )
        print()
        print(f"Dry run: {len(jobs)} job(s) planned; no changes made.")
        return 0

    print(f"Applying {len(jobs)} job(s) ...")
    try:
        created_profiles, created_jobs = apply_plan(
            actions, manifest, home, hermes_binary(args.hermes), state_file, state
        )
    except (RuntimeError, OSError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print()
    print(f"Done: {created_profiles} profile(s), {created_jobs} job(s) created/updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
