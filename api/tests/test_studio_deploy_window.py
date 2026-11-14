"""The app must never answer a customer with a bare "Internal Server Error".

Measured in production on 2026-11-14: an rsync left index.html momentarily unreadable (files
landed with the uploading user's permissions, chmod ran after) and the /studio route raised
PermissionError. Eight requests got "Internal Server Error" for the whole deploy window.
"""
import asyncio
import os
import pathlib
import uuid

import httpx
import pytest

from app import main as app_main
from app import owner_auth


def _client():
    user = {"id": str(uuid.uuid4()), "tenant_id": str(uuid.uuid4()), "email": "o@a.test",
            "role": "owner", "slug": "acme", "name": "Acme"}
    app_main.app.dependency_overrides[owner_auth.current_user] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app_main.app), base_url="http://t")


def _reset():
    app_main.app.dependency_overrides.clear()


def test_an_unreadable_index_answers_503_not_500(tmp_path, monkeypatch):
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><title>Studio</title>")
    monkeypatch.setattr(app_main, "STUDIO_DIR", tmp_path)

    async def run():
        async with _client() as client:
            healthy = await client.get("/studio")
            assert healthy.status_code == 200
            os.chmod(index, 0o000)
            try:
                broken = await client.get("/studio")
                assert broken.status_code == 503, (
                    "an unreadable index must say 'one moment', never crash with a 500")
                assert "One moment" in broken.text
                assert broken.headers.get("retry-after") == "5"
                fallback = await client.get("/studio/some/deep/route")
                assert fallback.status_code == 503
            finally:
                os.chmod(index, 0o644)
            recovered = await client.get("/studio")
            assert recovered.status_code == 200
    _reset()
    asyncio.run(run())


def test_a_missing_asset_is_a_404_not_a_crash(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    good = tmp_path / "assets" / "app-abc123.js"
    good.write_text("console.log(1)")
    (tmp_path / "index.html").write_text("<!doctype html><title>Studio</title>")
    monkeypatch.setattr(app_main, "STUDIO_DIR", tmp_path)

    async def run():
        async with _client() as client:
            assert (await client.get("/studio/assets/app-abc123.js")).status_code == 200
            assert (await client.get("/studio/assets/app-gone999.js")).status_code == 404
            os.chmod(good, 0o000)
            try:
                unreadable = await client.get("/studio/assets/app-abc123.js")
                assert unreadable.status_code == 404, "unreadable asset must not 500"
            finally:
                os.chmod(good, 0o644)
    _reset()
    asyncio.run(run())


def test_the_deploy_script_sets_permissions_before_files_go_live():
    """The portal deploy must not leave a window where files are unreadable by the API user."""
    script = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps" / "deploy-studio.sh"
    assert script.exists(), "there is no atomic portal deploy script"
    body = script.read_text()
    assert "--chmod=" in body, "rsync must set readable permissions as files land"
    assert "curl" in body and "200" in body, "the deploy must verify the page actually serves"
