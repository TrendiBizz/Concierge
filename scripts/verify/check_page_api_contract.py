#!/usr/bin/env python3
"""Fail when a website page calls an /api/ endpoint that nothing serves.

Background (2026-11-24): /api/robots was served by a Cloudflare-era worker that the VPS cutover removed. The page
kept calling it, the endpoint answered 404, and nothing in CI or the deploy noticed. This scan makes that class
of break loud:

  * every website/**/*.js and *.html is scanned for quoted "/api/..." paths (fetch calls, constants, form actions);
  * each path must be declared by a FastAPI route under api/app (@router.get/post/...("/api/..."));
  * each path must be matched by a Caddy handler on host trendibizz.com that reverse-proxies to api:8000.

Usage: check_page_api_contract.py [REPO_ROOT] [--paths]     Exit 0 = every called path is served, 1 = something is not.
Imported by api/tests/test_page_api_contract.py and run by scripts/seo-gate.sh.
"""
from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path

PAGE_HOST = "trendibizz.com"
CALL_RE = re.compile(r"""["'`](/api/[A-Za-z0-9_\-./]*[A-Za-z0-9_\-])(?=["'`?#/\s)])""")
ROUTE_RE = re.compile(r"""@\w+\.(get|post|put|patch|delete|options|head|api_route)\(\s*["'](/api/[^"']*)["']""")
SKIP_DIRS = {"node_modules", ".git", "__pycache__"}


METHOD_RE = re.compile(r"""method\s*:\s*["'`](\w+)["'`]""", re.I)


def page_calls(root: Path) -> dict[str, dict]:
    """Map each /api/ path the pages mention to {"files": [...], "methods": {...}}.

    The method is read from the options object right after the path (`fetch("/api/x", {method: "POST"`); a bare
    mention counts as GET. The route must serve that method, so a GET-only liveness route cannot stand in for a
    POST endpoint."""
    found: dict[str, dict] = {}
    for path in sorted((root / "website").rglob("*")):
        if path.suffix not in (".js", ".html", ".mjs") or SKIP_DIRS & set(path.parts) or path.name.startswith("._"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in CALL_RE.finditer(text):
            entry = found.setdefault(match.group(1).rstrip("/"), {"files": [], "methods": set()})
            entry["files"].append(str(path.relative_to(root)))
            following = METHOD_RE.search(text[match.end():match.end() + 160])
            entry["methods"].add(following.group(1).upper() if following else "GET")
    return found


def api_routes(root: Path) -> dict[str, set[str]]:
    routes: dict[str, set[str]] = {}
    for path in sorted((root / "api" / "app").rglob("*.py")):
        for method, route in ROUTE_RE.findall(path.read_text(encoding="utf-8", errors="replace")):
            routes.setdefault(route.rstrip("/"), set()).add(method.upper())
    return routes


def caddy_api_paths(root: Path, host: str = PAGE_HOST) -> list[str]:
    """Path patterns that Caddy sends to api:8000 for `host` (named matcher + handle block)."""
    text = (root / "scripts" / "vps" / "Caddyfile").read_text(encoding="utf-8")
    matchers: dict[str, dict] = {}
    for m in re.finditer(r"^\s*@(\w+)\s*\{(.*?)^\s*\}", text, re.S | re.M):
        body = m.group(2)
        hosts = [h for line in re.findall(r"^\s*host\s+(.+)$", body, re.M) for h in line.split()]
        paths = [p for line in re.findall(r"^\s*path\s+(.+)$", body, re.M) for p in line.split()]
        matchers[m.group(1)] = {"hosts": hosts, "paths": paths}
    patterns: list[str] = []
    for m in re.finditer(r"^\s*handle\s+@(\w+)\s*\{", text, re.M):
        depth, i = 1, m.end()
        while depth and i < len(text):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        block = text[m.end():i]
        spec = matchers.get(m.group(1))
        if spec and host in spec["hosts"] and re.search(r"reverse_proxy\s+api:\d+", block):
            patterns += spec["paths"]
    return patterns


def check(root: Path) -> list[str]:
    problems: list[str] = []
    routes, caddy = api_routes(root), caddy_api_paths(root)
    calls = page_calls(root)
    if not calls:
        problems.append("no /api/ calls found under website/: the scan itself is broken")
    for call, info in sorted(calls.items()):
        where = ", ".join(sorted(set(info["files"]))[:3])
        if call not in routes:
            problems.append(f"{call} (called from {where}): no FastAPI route in api/app serves it")
        else:
            for method in sorted(info["methods"] - routes[call]):
                problems.append(f"{call} (called from {where}): no FastAPI route serves {method} on it (has {', '.join(sorted(routes[call]))})")
        if not any(fnmatch.fnmatchcase(call, pattern) for pattern in caddy):
            problems.append(f"{call} (called from {where}): no Caddy handler for host {PAGE_HOST} sends it to api:8000")
    return problems


def main(argv: list[str]) -> int:
    paths_only = "--paths" in argv  # print one called path per line (used by verify-deploy.sh's drift guard)
    argv = [a for a in argv if a != "--paths"]
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[2]
    calls = page_calls(root)
    if paths_only:
        print("\n".join(sorted(calls)))
        return 0
    problems = check(root)
    for call in sorted(calls):
        print(f"  {call}")
    if problems:
        print("PAGE API CONTRACT: FAIL")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"PAGE API CONTRACT: OK ({len(calls)} endpoints called by pages, each served by FastAPI and routed by Caddy)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
