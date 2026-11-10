#!/usr/bin/env python3
"""List every route the API serves, as full paths, for the gateway audit.

Pairs each `@router` path with its OWN module's prefix. An earlier shell version cross-multiplied
every router route against every prefix, inventing paths that never existed and then reporting them
as blocked at the edge -- a confident false result. Doing it per module avoids that entirely.

Usage: gateway_route_list.py <repo_root>
"""
import glob
import os
import re
import sys

DECORATOR = re.compile(
    r'@(app|router)\.(get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']'
)
PREFIX = re.compile(r'APIRouter\(prefix=["\']([^"\']+)["\']')


def routes(repo: str) -> list[str]:
    found = set()
    for path in glob.glob(os.path.join(repo, "api", "app", "*.py")):
        with open(path) as handle:
            src = handle.read()
        match = PREFIX.search(src)
        prefix = match.group(1) if match else ""
        for dec in DECORATOR.finditer(src):
            owner, route = dec.group(1), dec.group(3)
            full = (prefix + route) if owner == "router" else route
            if full.startswith(("/api/v1/", "/owner/")):
                found.add(full)
    return sorted(found)


if __name__ == "__main__":
    for route in routes(sys.argv[1]):
        print(route)
