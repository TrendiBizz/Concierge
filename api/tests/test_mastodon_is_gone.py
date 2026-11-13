"""Mastodon was removed from the product; it must not creep back.

It was never supported on this deployment — no credentials, a bridge that answered 503, and an
owner-facing button that produced `error code: 502`. Removing the endpoints is the fix; this test
fails if a route, a status flag or an owner-facing reference to it returns.
"""

import pathlib
import re

from app.main import app

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
STATIC = pathlib.Path(__file__).resolve().parents[1] / "static"


def test_no_mastodon_routes_exist():
    paths = app.openapi()["paths"]
    offenders = [path for path in paths if "mastodon" in path.lower()]
    assert not offenders, "mastodon endpoints are back: " + ", ".join(offenders)


def test_the_status_payload_does_not_advertise_mastodon():
    import asyncio

    from app import main

    result = asyncio.run(main.owner_social_status({"slug": "pukeko-construction", "role": "owner"}))
    assert "mastodon" not in result["providers"]


def test_no_server_or_client_code_mentions_mastodon():
    hits = []
    for folder, suffix in ((APP, ".py"), (STATIC, ".html")):
        for source in folder.glob("*" + suffix):
            text = source.read_text(errors="ignore").lower()
            for match in re.finditer(r"mastodon", text):
                line = text[: match.start()].count("\n") + 1
                hits.append(f"{source.name}:{line}")
    assert not hits, "mastodon references remain: " + ", ".join(hits)
