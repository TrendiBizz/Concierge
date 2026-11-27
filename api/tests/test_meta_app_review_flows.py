"""End-to-end tests for Meta App Review flows (all 6 permissions).

Covers:
- Exact 6-scope Facebook Login (User OAuth 2.0) URL & status metadata
- OAuth finish persisting encrypted long-lived user token + Page/IG avatars
- Page picker (pages_show_list + instagram_basic)
- Business picker + Link Page to business (business_management: owned, client, 3944 already-linked)
- Page activity view (pages_read_engagement: followers, posts, engagement, photos)
- Immediate publish-now to Facebook Page + Instagram with caption + image + live permalink URLs
  (pages_manage_posts + instagram_content_publish)
- Studio UI static checks for English labels, tooltips, and copy hygiene
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import re
from urllib.parse import parse_qs, urlsplit

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import crypto_vault, db, owner_auth, social, tenants
from app.config import get_settings
from app.main import app

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()
EXPECTED_SIX_SCOPES = [
    "pages_show_list",
    "pages_manage_posts",
    "pages_read_engagement",
    "business_management",
    "instagram_basic",
    "instagram_content_publish",
]


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "384"))
    db._pool = pool
    return pool


def run(fn):
    async def wrapper():
        pool = await _fresh_pool()
        try:
            await fn(pool)
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(wrapper())


def _configure_meta(monkeypatch, *, live: bool = False):
    s = get_settings()
    cb = "https://concierge.trendibizz.com/owner/social/oauth/callback"
    monkeypatch.setattr(s, "social_service_enabled", True, raising=False)
    monkeypatch.setattr(s, "social_live_publishing", live, raising=False)
    monkeypatch.setattr(s, "social_enable_facebook_publish", live, raising=False)
    monkeypatch.setattr(s, "social_enable_instagram_publish", live, raising=False)
    monkeypatch.setattr(s, "social_facebook_client_id", "676274422041376", raising=False)
    monkeypatch.setattr(s, "social_facebook_client_secret", "test-meta-secret", raising=False)
    monkeypatch.setattr(s, "social_facebook_callback", cb, raising=False)
    monkeypatch.setattr(s, "social_instagram_login_mode", "facebook", raising=False)
    monkeypatch.setattr(s, "meta_graph_version", "v22.0", raising=False)


@needs_db
def test_meta_oauth_scopes_page_picker_business_link_activity_and_publish(monkeypatch):
    _configure_meta(monkeypatch, live=False)

    async def _go(pool):
        t = await tenants.create("Harbour Trade Co", "https://harbour.example", "harbour-trade")
        inv = await owner_auth.make_invite(t["id"], "owner@harbour.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        called_urls: list[tuple[str, str]] = []

        async def fake_oauth_http(method, url, *, headers=None, params=None, data=None, json_body=None, auth=None, timeout=15.0):
            called_urls.append((method, url))
            if url.endswith("/oauth/access_token") and params and params.get("grant_type") == "fb_exchange_token":
                return 200, {"access_token": "long-lived-user-tok", "expires_in": 5184000}
            if url.endswith("/oauth/access_token"):
                return 200, {"access_token": "short-lived-user-tok", "expires_in": 3600}
            if url.endswith("/debug_token"):
                return 200, {
                    "data": {
                        "is_valid": True,
                        "app_id": "676274422041376",
                        "user_id": "900001",
                        "scopes": EXPECTED_SIX_SCOPES,
                    }
                }
            if url.endswith("/me"):
                return 200, {"id": "900001", "name": "Harbour Demo Owner"}
            if url.endswith("/me/accounts"):
                return 200, {
                    "data": [
                        {
                            "id": "111222333444",
                            "name": "Harbour Trade NZ",
                            "access_token": "page-token-secret-1",
                            "category": "Home Improvement",
                            "fan_count": 410,
                            "followers_count": 428,
                            "tasks": ["CREATE_CONTENT", "MODERATE", "ANALYZE", "MANAGE"],
                            "picture": {"data": {"url": "https://cdn.example/page-avatar.jpg"}},
                            "instagram_business_account": {
                                "id": "555666777888",
                                "username": "harbourtradenz",
                                "profile_picture_url": "https://cdn.example/ig-avatar.jpg",
                                "followers_count": 312,
                            },
                        },
                        {
                            "id": "999888777666",
                            "name": "Harbour Commercial",
                            "access_token": "page-token-secret-2",
                            "category": "Contractor",
                            "fan_count": 90,
                            "followers_count": 95,
                            "tasks": ["CREATE_CONTENT", "ANALYZE"],
                            "picture": {"data": {"url": "https://cdn.example/page2.jpg"}},
                        },
                    ]
                }
            if url.endswith("/me/businesses"):
                return 200, {
                    "data": [
                        {
                            "id": "777000111222",
                            "name": "Harbour Group Business",
                            "profile_picture_uri": "https://cdn.example/biz.jpg",
                            "verification_status": "verified",
                        }
                    ]
                }
            if method == "GET" and url.endswith("/777000111222/owned_pages"):
                return 200, {"data": [{"id": "111222333444", "name": "Harbour Trade NZ"}]}
            if method == "GET" and url.endswith("/777000111222/client_pages"):
                return 200, {"data": []}
            if method == "POST" and url.endswith("/777000111222/owned_pages"):
                assert data and data.get("page_id") in ("111222333444", "999888777666")
                if data["page_id"] == "999888777666":
                    return 400, {"error": {"code": 3944, "message": "Your Business Manager already has access to this object"}}
                return 200, {"success": True, "access_status": "CONFIRMED"}
            if method == "POST" and url.endswith("/777000111222/client_pages"):
                assert data and "CREATE_CONTENT" in (data.get("permitted_tasks") or "")
                return 200, {"success": True, "access_status": "PENDING"}
            if method == "GET" and url.endswith("/111222333444"):
                return 200, {
                    "id": "111222333444",
                    "name": "Harbour Trade NZ",
                    "category": "Home Improvement",
                    "link": "https://www.facebook.com/harbourtradenz",
                    "fan_count": 410,
                    "followers_count": 428,
                    "picture": {"data": {"url": "https://cdn.example/page-avatar.jpg"}},
                    "instagram_business_account": {
                        "id": "555666777888",
                        "username": "harbourtradenz",
                        "profile_picture_url": "https://cdn.example/ig-avatar.jpg",
                        "followers_count": 312,
                    },
                }
            if method == "GET" and url.endswith("/111222333444/posts"):
                return 200, {
                    "data": [
                        {
                            "id": "111222333444_101",
                            "message": "Deck build completed in Devonport!",
                            "created_time": "2026-11-25T08:00:00+0000",
                            "permalink_url": "https://www.facebook.com/harbourtradenz/posts/101",
                            "full_picture": "https://cdn.example/post101.jpg",
                            "likes": {"summary": {"total_count": 24}},
                            "comments": {"summary": {"total_count": 5}},
                            "shares": {"count": 3},
                        }
                    ]
                }
            if method == "GET" and url.endswith("/111222333444/photos"):
                return 200, {
                    "data": [
                        {
                            "id": "photo_1",
                            "name": "Finished cedar deck",
                            "images": [{"source": "https://cdn.example/photo1.jpg"}],
                            "link": "https://www.facebook.com/photo/?fbid=1",
                            "created_time": "2026-11-24T08:00:00+0000",
                        }
                    ]
                }
            raise AssertionError(f"Unexpected Meta HTTP call: {method} {url}")

        monkeypatch.setattr(social.oauth, "_http_json", fake_oauth_http)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Verify status returns exact 6 Meta scopes
            st = await client.get("/owner/social/status", headers=headers)
            assert st.status_code == 200
            assert st.json()["meta_scopes"] == EXPECTED_SIX_SCOPES

            # 2. Verify Facebook Login URL asks for the EXACT 6 scopes and nothing else
            start = await client.post("/owner/social/oauth/meta/facebook/start", headers=headers)
            assert start.status_code == 200
            start_data = start.json()
            qs = parse_qs(urlsplit(start_data["authorization_url"]).query)
            assert qs["scope"][0].split(",") == EXPECTED_SIX_SCOPES
            assert "pages_messaging" not in qs["scope"][0]
            assert "pages_manage_metadata" not in qs["scope"][0]

            # 3. Finish OAuth -> stores encrypted user token, connects Pages + linked IG, skips webhook subscribe
            fin = await client.post(
                "/owner/social/oauth/meta/facebook/finish",
                headers=headers,
                json={"state": start_data["state"], "code": "oauth-code-123"},
            )
            assert fin.status_code == 200, fin.text
            fin_body = fin.json()
            assert "page-token-secret" not in str(fin_body)
            assert "long-lived-user-tok" not in str(fin_body)
            assert not any("subscribed_apps" in u for _, u in called_urls)

            # Verify user token is encrypted at rest in social_meta_sessions
            raw_tok = await pool.fetchval(
                "SELECT user_token_enc FROM social_meta_sessions WHERE customer_slug='harbour-trade'"
            )
            assert crypto_vault.is_encrypted(raw_tok)

            # 4. Page Picker: returns Page name, avatar, followers, and linked Instagram account
            pg_res = await client.get("/owner/social/meta/pages", headers=headers)
            assert pg_res.status_code == 200, pg_res.text
            pg_body = pg_res.json()
            assert pg_body["connected"] is True
            assert len(pg_body["pages"]) == 2
            first_page = pg_body["pages"][0]
            assert first_page["name"] == "Harbour Trade NZ"
            assert first_page["avatar_url"] == "https://cdn.example/page-avatar.jpg"
            assert first_page["followers_count"] == 428
            assert first_page["instagram"]["username"] == "harbourtradenz"
            assert first_page["instagram"]["avatar_url"] == "https://cdn.example/ig-avatar.jpg"
            assert "access_token" not in str(pg_body)

            # Select Page explicitly via Page Picker
            sel_res = await client.post(
                "/owner/social/meta/pages/select",
                headers=headers,
                json={"page_id": "111222333444", "include_instagram": True},
            )
            assert sel_res.status_code == 200, sel_res.text
            sel_body = sel_res.json()
            assert sel_body["ok"] is True
            assert "Harbour Trade NZ" in sel_body["message"]
            assert "@harbourtradenz" in sel_body["message"]
            fb_account_id = sel_body["facebook_account_id"]
            ig_account_id = sel_body["instagram_account_id"]
            assert fb_account_id and ig_account_id

            # 5. Business Picker + Link Page to Business (owned, already-linked 3944, and client)
            biz_res = await client.get("/owner/social/meta/businesses", headers=headers)
            assert biz_res.status_code == 200, biz_res.text
            biz_body = biz_res.json()
            assert biz_body["granted_business_management"] is True
            assert biz_body["businesses"][0]["name"] == "Harbour Group Business"

            link_owned = await client.post(
                "/owner/social/meta/businesses/link-page",
                headers=headers,
                json={"business_id": "777000111222", "page_id": "111222333444", "relation": "owned"},
            )
            assert link_owned.status_code == 200, link_owned.text
            assert link_owned.json()["ok"] is True
            assert link_owned.json()["access_status"] == "CONFIRMED"
            assert "Harbour Group Business" in link_owned.json()["message"]

            link_already = await client.post(
                "/owner/social/meta/businesses/link-page",
                headers=headers,
                json={"business_id": "777000111222", "page_id": "999888777666", "relation": "owned"},
            )
            assert link_already.status_code == 200, link_already.text
            assert link_already.json()["access_status"] == "ALREADY_LINKED"

            link_client = await client.post(
                "/owner/social/meta/businesses/link-page",
                headers=headers,
                json={"business_id": "777000111222", "page_id": "111222333444", "relation": "client"},
            )
            assert link_client.status_code == 200, link_client.text
            assert link_client.json()["access_status"] == "PENDING"

            # 6. Page Activity (pages_read_engagement): returns Page identity, followers, posts, engagement, photos
            act_res = await client.get(f"/owner/social/meta/pages/{fb_account_id}/activity", headers=headers)
            assert act_res.status_code == 200, act_res.text
            act_body = act_res.json()
            assert act_body["page"]["name"] == "Harbour Trade NZ"
            assert act_body["page"]["avatar_url"] == "https://cdn.example/page-avatar.jpg"
            assert act_body["page"]["followers_count"] == 428
            assert act_body["totals"] == {"posts": 1, "likes": 24, "comments": 5, "shares": 3}
            assert act_body["posts"][0]["permalink_url"] == "https://www.facebook.com/harbourtradenz/posts/101"
            assert len(act_body["photos"]) == 1

            # 7. Publish Now safety: blocked while live publishing is disabled
            draft = await client.post(
                "/owner/social/posts",
                headers=headers,
                json={
                    "content": "Fresh cedar deck complete in Auckland.",
                    "account_ids": [fb_account_id, ig_account_id],
                    "media": ["https://cdn.example/deck-photo.jpg"],
                },
            )
            assert draft.status_code == 200, draft.text
            post_id = draft.json()["id"]

            blocked = await client.post(f"/owner/social/posts/{post_id}/publish-now", headers=headers)
            assert blocked.status_code == 409

            # 8. Publish Now to BOTH Facebook Page + Instagram with caption + image -> returns BOTH live permalinks!
            _configure_meta(monkeypatch, live=True)

            async def fake_publish_http(method, url, *, headers=None, params=None, json_body=None, data=None, max_retries=2, timeout=20.0):
                if method == "POST" and url.endswith("/111222333444/photos"):
                    assert data["caption"] == "Fresh cedar deck complete in Auckland."
                    assert data["url"] == "https://cdn.example/deck-photo.jpg"
                    return 200, {"id": "photo_888", "post_id": "111222333444_888"}, 0
                if method == "GET" and url.endswith("/111222333444_888"):
                    return 200, {"permalink_url": "https://www.facebook.com/harbourtradenz/posts/888"}, 0
                if method == "POST" and url.endswith("/555666777888/media"):
                    assert data["image_url"] == "https://cdn.example/deck-photo.jpg"
                    assert data["caption"] == "Fresh cedar deck complete in Auckland."
                    return 200, {"id": "creation_777"}, 0
                if method == "GET" and "creation_777" in url:
                    return 200, {"status_code": "FINISHED"}, 0
                if method == "POST" and url.endswith("/555666777888/media_publish"):
                    assert data["creation_id"] == "creation_777"
                    return 200, {"id": "ig_media_999"}, 0
                if method == "GET" and url.endswith("/ig_media_999"):
                    return 200, {"id": "ig_media_999", "permalink": "https://www.instagram.com/p/CxHarbour999/"}, 0
                raise AssertionError(f"Unexpected publish HTTP call: {method} {url}")

            monkeypatch.setattr(social.publishers, "_request_with_retry", fake_publish_http)

            pub = await client.post(f"/owner/social/posts/{post_id}/publish-now", headers=headers)
            assert pub.status_code == 200, pub.text
            pub_body = pub.json()
            assert pub_body["status"] == "published"
            by_net = {r["network"]: r for r in pub_body["results"]}
            assert by_net["facebook"]["ok"] is True
            assert by_net["facebook"]["external_url"] == "https://www.facebook.com/harbourtradenz/posts/888"
            assert by_net["instagram"]["ok"] is True
            assert by_net["instagram"]["external_url"] == "https://www.instagram.com/p/CxHarbour999/"

    run(_go)


def test_social_ui_has_meta_review_flows_tooltips_and_clean_copy():
    engage = (pathlib.Path(__file__).resolve().parents[2] / "web" / "portal" / "src" / "Engage.tsx").read_text(encoding="utf-8")
    for required in (
        "Continue with Facebook",
        "Facebook Page &amp; Instagram picker",
        "Meta Business Portfolio",
        "Link Page to business",
        "Page activity",
        "Load Page activity",
        "Publish to selected accounts now",
        "TipWrap",
        "pages_show_list",
        "pages_manage_posts",
        "pages_read_engagement",
        "business_management",
        "instagram_basic",
        "instagram_content_publish",
    ):
        assert required in engage, f"Missing expected Meta App Review UI element: {required}"
    # Guard against forbidden promotional word in Social UI copy
    social_section = engage[engage.index("export function Social"):]
    assert not re.search(r"\bfree\b", social_section, re.IGNORECASE), "Copy must not use the word 'free'"
