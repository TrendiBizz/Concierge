"""Every API path the Studio portal calls must actually exist.

Designs.tsx called `/owner/crm/leads` for the customer picker. There is no such route — the list
lives on `/owner/crm` — so the picker silently rendered an empty list and a measured model could
never be turned into a quotation. Nothing failed: the catch block swallowed the 404 and showed
"No enquiries yet". This test reads the portal source and checks each literal path against the
API's own route table, so a typo'd or invented endpoint fails in CI instead of in front of the
customer.
"""

import pathlib
import re

from app.main import app

PORTAL = pathlib.Path(__file__).resolve().parents[2] / "web" / "portal" / "src"

CALL = re.compile(r"""\bapi\(\s*['"]([^'"`]+)['"]""")


def portal_paths() -> dict[str, bool]:
    """Literal API paths used by the portal, mapped to whether they are built by concatenation.

    `api('/owner/media/' + kind)` ends in a slash: only its prefix is literal, so any real route
    below it satisfies it. `api('/owner/crm/leads')` is a complete path and must exist exactly —
    that is the case this test exists for.
    """
    found: dict[str, bool] = {}
    for source in PORTAL.glob("*.tsx"):
        for match in CALL.finditer(source.read_text()):
            raw = match.group(1)
            if not raw.startswith("/"):
                continue
            clean = raw.split("?")[0].split("${")[0]
            if not (clean.startswith("/owner") or clean.startswith("/api")):
                continue
            open_ended = clean.endswith("/")
            found[clean.rstrip("/") or "/"] = open_ended
    return found


def api_paths() -> set[str]:
    return {path.rstrip("/") or "/" for path in app.openapi()["paths"]}


def test_the_portal_source_was_found():
    assert PORTAL.is_dir(), "portal source moved - this guard would silently pass"
    assert len(portal_paths()) > 10


def test_every_portal_api_path_exists_in_the_api():
    known = api_paths()
    missing = []
    for path, open_ended in sorted(portal_paths().items()):
        if path in known:
            continue
        if open_ended and any(route.startswith(path.rstrip("/") + "/") for route in known):
            continue
        missing.append(path)
    assert not missing, "portal calls endpoints that do not exist:\n  " + "\n  ".join(missing)
