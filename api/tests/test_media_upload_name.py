"""An uploaded photo keeps its own name.

Three solid-green test uploads sat in Marketing media, all captioned "Image", indistinguishable
from each other and from anything real. The upload handler built a name from a hash and threw the
customer's filename away, so the UI had nothing better to show.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import db, main, media_studio, owner_auth

TENANT = "11111111-1111-1111-1111-111111111111"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_a_path_is_reduced_to_its_filename():
    assert media_studio.safe_original_name("C:\\Users\\jo\\Desktop\\kitchen.jpg") == "kitchen.jpg"
    assert media_studio.safe_original_name("/var/tmp/front door.png") == "front door.png"


def test_control_characters_and_separators_cannot_get_through():
    assert media_studio.safe_original_name("bad<>:\"name|?.jpg") == "badname.jpg"
    assert media_studio.safe_original_name("../../etc/passwd") == "passwd"


def test_a_long_name_is_capped_and_a_missing_one_is_empty():
    assert len(media_studio.safe_original_name("x" * 400)) == 120
    assert media_studio.safe_original_name("") == ""
    assert media_studio.safe_original_name("   ...   ") == ""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """The real upload route, writing into a temp media dir, with the database substituted."""
    async def auth():
        return {"tenant_id": TENANT, "id": "u1", "email": "o@a.example", "role": "owner"}

    main.app.dependency_overrides[owner_auth.current_user] = auth
    monkeypatch.setattr(media_studio.get_settings(), "media_dir", str(tmp_path), raising=False)
    captured = {}

    def fake_fetchrow(sql, *args):
        """The real _store writes the file, then asks for the row back; hand it the real path."""
        captured["args"] = args
        written = [f for f in tmp_path.rglob("*") if f.is_file()]
        # RETURNING * would include the name the INSERT was given, which is args[-1]
        return {"id": "asset-1", "storage_path": str(written[0]), "original_name": args[-1]}

    pool = SimpleNamespace(
        fetchval=AsyncMock(return_value=0),
        fetchrow=AsyncMock(side_effect=fake_fetchrow),
        execute=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(db, "pool", lambda: pool)
    yield TestClient(main.app), captured
    main.app.dependency_overrides.clear()


def test_the_upload_stores_the_customers_filename(client):
    http, captured = client
    response = http.post("/owner/media/upload", content=PNG,
                         headers={"Content-Type": "image/png",
                                  "X-Filename": "kitchen%20before.jpg"})
    assert response.status_code == 201, response.text
    assert response.json()["original_name"] == "kitchen before.jpg"
    # the value reaches the INSERT, not just the response
    assert captured["args"][-1] == "kitchen before.jpg"


def test_an_upload_without_a_filename_still_works(client):
    http, captured = client
    response = http.post("/owner/media/upload", content=PNG, headers={"Content-Type": "image/png"})
    assert response.status_code == 201, response.text
    assert captured["args"][-1] == ""
