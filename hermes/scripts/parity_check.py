#!/usr/bin/env python3
"""Check that every command the old Grok/Workwatch bots ran is present and runnable for Hermes.

Run inside the container:
  docker exec hermes-concierge /opt/data/venvs/trendi-seo/bin/python /opt/data/work/hermes/scripts/parity_check.py

For each command: the file must exist, compile (py_compile / bash -n) and, for Python
scripts, every imported module must resolve in the venv. Nothing is executed for
real: no network, no writes, no posting. Exit 1 if any REQUIRED command is not OK.
"""
import py_compile
import subprocess
import sys
from pathlib import Path

SEO = Path("/opt/data/OpenBot/Shared/trendi-seo")
SITE = Path("/opt/data/OpenBot/Shared/trendi-site")
WW = Path("/opt/data/OpenBot/Shared/workwatch")
PY = "/opt/data/venvs/trendi-seo/bin/python"

# (agent, label, path, kind, help_ok)  kind: py | sh | doc
COMMANDS = [
    ("seo-engine", "daily monitor", SEO / "monitor/daily_monitor.py", "py", True),
    ("seo-engine", "SERP check", SEO / "monitor/serp_check.py", "py", True),
    ("seo-engine", "crawl audit", SEO / "audits/crawl.py", "py", True),
    ("seo-engine", "GSC audit", SEO / "audits/gsc.py", "py", True),
    ("seo-engine", "PageSpeed audit", SEO / "audits/psi.py", "py", True),
    ("seo-engine", "IndexNow", SEO / "audits/indexnow.py", "py", True),
    ("seo-engine", "25-prompt AI panel", SEO / "ai_panel/run_panel.py", "py", True),
    ("seo-engine", "index coverage (inspect_sitemap)", SEO / "coverage/inspect_sitemap.py", "py", True),
    ("seo-engine", "citations aggregate", SEO / "citations/aggregate.py", "py", True),
    ("seo-engine", "DataForSEO weekly (--dry-run)", SEO / "dataforseo/weekly.py", "py", True),
    ("seo-engine", "ship gate seo-gate.sh", SITE / "scripts/seo-gate.sh", "sh", False),
    ("trendi-desk", "offer facts PRODUCT.md", SITE / "PRODUCT.md", "doc", False),
    ("trendi-desk", "tamper watch daily_watch.py", WW / "tamper-watch/security/daily_watch.py", "py", True),
    ("workwatch", "run_social.sh", WW / "ops/bin/run_social.sh", "sh", False),
    ("workwatch", "run_deep_dive.sh", WW / "ops/bin/run_deep_dive.sh", "sh", False),
    ("workwatch", "check_social.py", WW / "ops/bin/check_social.py", "py", False),
    ("workwatch", "fetch_sources.py", WW / "ops/bin/fetch_sources.py", "py", False),
]


def check(agent, label, path, kind, help_ok):
    if not path.is_file():
        return "MISSING", str(path)
    try:
        if kind == "py":
            py_compile.compile(str(path), doraise=True, cfile="/tmp/parity.pyc")
        elif kind == "sh":
            r = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True, timeout=20)
            if r.returncode:
                return "BROKEN", r.stderr.strip()[:120]
    except Exception as e:  # compile error
        return "BROKEN", str(e)[:120]
    if kind == "py" and help_ok:
        # Static import check: never run the script (daily_monitor has no --help and would
        # start a real monitor run). Every imported module must resolve from the script's
        # directory or the trendi-seo root, using the venv interpreter.
        probe = (
            "import ast,importlib.util,sys;"
            "p=sys.argv[1];sys.path[:0]=[sys.argv[2],sys.argv[3],sys.argv[3]+'/audits'];"
            "mods={n.names[0].name.split('.')[0] for n in ast.walk(ast.parse(open(p).read())) if isinstance(n,ast.Import)}|"
            "{n.module.split('.')[0] for n in ast.walk(ast.parse(open(p).read())) if isinstance(n,ast.ImportFrom) and n.module and n.level==0};"
            "miss=sorted(m for m in mods if importlib.util.find_spec(m) is None);"
            "print(','.join(miss));sys.exit(1 if miss else 0)"
        )
        try:
            r = subprocess.run([PY, "-c", probe, str(path), str(path.parent), str(SEO)],
                               capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return "BROKEN", "import check timed out"
        if r.returncode != 0:
            return "BROKEN", "unresolved imports: " + (r.stdout.strip() or r.stderr.strip())[:100]
    return "OK", str(path)


def main():
    bad = 0
    for row in COMMANDS:
        status, detail = check(*row)
        if status != "OK":
            bad += 1
        print(f"{status:8} {row[0]:12} {row[1]:36} {detail if status != 'OK' else ''}")
    print(f"\n{len(COMMANDS) - bad}/{len(COMMANDS)} OK")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
