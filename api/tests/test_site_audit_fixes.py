"""Defects from the 14 Nov 2026 trendibizz.com link/menu audit that live in this repo.

Three of the audit's findings are ours to fix here: the bare owner host answered 404, every page
in the owner app logged a favicon 404, and a real-looking mobile number was the placeholder in
someone else's business-number field.
"""
import asyncio
import pathlib

import httpx

from app import main as app_main

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://concierge.trendibizz.com"


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app), base_url=BASE)


def test_the_bare_owner_host_sends_you_to_the_app():
    """Typing the hostname gave a 404 with no way forward. It must land on /owner-ui."""

    async def run():
        async with _client() as client:
            response = await client.get("/", follow_redirects=False)
        assert response.status_code in (307, 308), f"root answered {response.status_code}"
        assert response.headers["location"] == "/owner-ui"

    asyncio.run(run())


def test_the_owner_app_serves_a_favicon_instead_of_404():
    """Every page in the owner app logged one console error: /favicon.ico 404."""

    async def run():
        async with _client() as client:
            for path in ("/favicon.ico", "/favicon.svg"):
                response = await client.get(path)
                assert response.status_code == 200, f"{path} answered {response.status_code}"
                assert response.headers["content-type"].startswith("image/")
                assert len(response.content) > 100

    asyncio.run(run())


def test_no_real_looking_phone_number_is_used_as_a_placeholder():
    """The business-number field invited customers to type +64278817368 — a real NZ mobile.

    A placeholder must be obviously fake, or people submit it as their own number.
    """
    page = (ROOT / "static" / "owner.html").read_text()
    assert 'placeholder="+64278817368"' not in page, "a real phone number is back as a placeholder"
    assert 'placeholder="+64211234567"' in page
    placeholders = page.split('placeholder="')[1:]
    for value in (chunk.split('"', 1)[0] for chunk in placeholders):
        digits = "".join(ch for ch in value if ch.isdigit())
        if value.startswith("+") and len(digits) > 8:
            assert digits.startswith("6421"), f"placeholder {value!r} is not an obvious dummy"
