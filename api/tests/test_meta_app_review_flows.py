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
        "Recent Page photos",
        "No photos yet",
        "meta-error-box",
        "businessLinkError",
        'referrerPolicy="no-referrer"',
    ):
        assert required in engage, f"Missing expected Meta App Review UI element: {required}"
    # Guard against forbidden promotional word in Social UI copy
    social_section = engage[engage.index("export function Social"):]
    assert not re.search(r"\bfree\b", social_section, re.IGNORECASE), "Copy must not use the word 'free'"


def test_studio_csp_allows_meta_cdn_images():
    from app.security import STUDIO_CSP

    img_src = next(part.strip() for part in STUDIO_CSP.split(";") if part.strip().startswith("img-src"))
    for origin in ("https://*.fbcdn.net", "https://*.fbsbx.com", "https://*.cdninstagram.com", "https://graph.facebook.com"):
        assert origin in img_src, f"STUDIO_CSP img-src missing {origin}: {img_src}"


def test_public_media_base_prefers_studio_origin_over_chat_host(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "public_base_url", "https://chat.trendibizz.com", raising=False)
    monkeypatch.setattr(s, "social_facebook_callback", "https://concierge.trendibizz.com/owner/social/oauth/callback", raising=False)
    monkeypatch.setattr(s, "social_public_media_base", "", raising=False)
    monkeypatch.delenv("SOCIAL_PUBLIC_MEDIA_BASE", raising=False)
    assert social.config.public_media_base_url() == "https://concierge.trendibizz.com"


@needs_db
def test_uploaded_png_publishes_to_fb_multipart_and_ig_public_jpeg_and_business_already_owned(tmp_path, monkeypatch):
    import io
    from PIL import Image

    _configure_meta(monkeypatch, live=True)
    s = get_settings()
    # Reproduce live VPS mismatch where PUBLIC_BASE_URL points to chat.trendibizz.com
    monkeypatch.setattr(s, "public_base_url", "https://chat.trendibizz.com", raising=False)
    monkeypatch.setattr(s, "social_media_dir", str(tmp_path / "social-media"), raising=False)
    monkeypatch.delenv("SOCIAL_PUBLIC_MEDIA_BASE", raising=False)

    async def _go(pool):
        t = await tenants.create("Trendi Live Test", "https://trendi.example", "trendi-live-test")
        inv = await owner_auth.make_invite(t["id"], "owner@trendi.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        await social.store.ensure_customer("trendi-live-test", "Trendi Live Test")
        fb_account_id = await social.store.upsert_verified_account(
            customer_slug="trendi-live-test",
            network="facebook",
            external_id="270235042840463",
            display_name="Trendi",
            access_token="fb-page-tok",
            granted_scopes=social.oauth.META_REVIEW_SCOPES,
        )
        ig_account_id = await social.store.upsert_verified_account(
            customer_slug="trendi-live-test",
            network="instagram",
            external_id="17841465235622550",
            display_name="trendi456",
            access_token="fb-page-tok",
            granted_scopes=social.oauth.META_REVIEW_SCOPES,
        )
        await social.store.upsert_meta_session(
            customer_slug="trendi-live-test",
            meta_user_id="900099",
            meta_user_name="Jo van der Burgh",
            user_access_token="user-tok-123",
            granted_scopes=social.oauth.META_REVIEW_SCOPES,
        )

        # Build a real RGBA PNG image (Meta Instagram rejects PNG; must normalize to RGB JPEG)
        img = Image.new("RGBA", (320, 320), (40, 140, 220, 200))
        png_buf = io.BytesIO()
        img.save(png_buf, format="PNG")
        png_bytes = png_buf.getvalue()

        captured: dict = {}

        async def fake_publish_http(
            method, url, *, headers=None, params=None, json_body=None, data=None, files=None, max_retries=2, timeout=20.0
        ):
            if method == "POST" and url.endswith("/270235042840463/photos"):
                captured["fb_files"] = files
                captured["fb_data"] = data
                assert files and "source" in files, "FB uploaded image should use multipart source"
                fname, fbytes, fmime = files["source"]
                assert fmime == "image/jpeg"
                assert fbytes[:3] == b"\xff\xd8\xff"
                return 200, {"id": "fb_photo_1", "post_id": "270235042840463_901"}, 0
            if method == "GET" and url.endswith("/270235042840463_901"):
                return 200, {"permalink_url": "https://www.facebook.com/270235042840463/posts/901"}, 0
            if method == "POST" and url.endswith("/17841465235622550/media"):
                captured["ig_image_url"] = (data or {}).get("image_url", "")
                return 200, {"id": "ig_creation_1"}, 0
            if method == "GET" and "ig_creation_1" in url:
                return 200, {"status_code": "FINISHED"}, 0
            if method == "POST" and url.endswith("/17841465235622550/media_publish"):
                return 200, {"id": "ig_media_1"}, 0
            if method == "GET" and url.endswith("/ig_media_1"):
                return 200, {"id": "ig_media_1", "permalink": "https://www.instagram.com/p/CTrendi901/"}, 0
            raise AssertionError(f"Unexpected publish HTTP call: {method} {url}")

        monkeypatch.setattr(social.publishers, "_request_with_retry", fake_publish_http)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Upload PNG -> stored as normalized JPEG
            up = await client.post(
                "/owner/social/media",
                headers={**headers, "Content-Type": "application/octet-stream"},
                content=png_bytes,
            )
            assert up.status_code == 200, up.text
            up_body = up.json()
            assert up_body["mime"] == "image/jpeg"
            media_ref = f"upload:{up_body['id']}"

            # 2. Create draft with uploaded ref & publish-now
            draft = await client.post(
                "/owner/social/posts",
                headers=headers,
                json={
                    "content": "Live photo upload test caption",
                    "account_ids": [fb_account_id, ig_account_id],
                    "media": [media_ref],
                },
            )
            assert draft.status_code == 200, draft.text
            post_id = draft.json()["id"]

            pub = await client.post(f"/owner/social/posts/{post_id}/publish-now", headers=headers)
            assert pub.status_code == 200, pub.text
            pub_body = pub.json()
            assert pub_body["status"] == "published"
            by_net = {r["network"]: r for r in pub_body["results"]}
            assert by_net["facebook"]["ok"] is True
            assert by_net["instagram"]["ok"] is True

            # 3. Verify IG received a public concierge.trendibizz.com JPEG URL that serves 200 on HEAD and GET
            ig_url = captured["ig_image_url"]
            assert ig_url.startswith("https://concierge.trendibizz.com/api/v1/social-media/sm1_"), ig_url
            assert ig_url.endswith(".jpg"), ig_url
            path = urlsplit(ig_url).path
            head_res = await client.head(path)
            assert head_res.status_code == 200, head_res.text
            assert head_res.headers["content-type"].startswith("image/jpeg")
            get_res = await client.get(path)
            assert get_res.status_code == 200
            assert get_res.headers["content-type"].startswith("image/jpeg")
            assert get_res.content[:3] == b"\xff\xd8\xff"

            # 4. Verify Business link already-owned (non-3944 Meta error + readback confirmation) AND real error
            async def fake_biz_http(method, url, *, headers=None, params=None, data=None, json_body=None, auth=None, timeout=15.0):
                if url.endswith("/me/businesses"):
                    return 200, {"data": [{"id": "801162021859410", "name": "Trendi", "primary_page": {"id": "270235042840463", "name": "Trendi"}}]}
                if method == "POST" and url.endswith("/801162021859410/owned_pages"):
                    if data and data.get("page_id") == "270235042840463":
                        return 400, {"error": {"code": 100, "message": "Invalid parameter: page cannot be claimed again"}}
                    return 400, {"error": {"code": 200, "message": "Permissions error: user lacks admin access on target page"}}
                if method == "GET" and url.endswith("/801162021859410/owned_pages"):
                    return 200, {"data": [{"id": "270235042840463", "name": "Trendi"}]}
                if method == "GET" and url.endswith("/me/accounts"):
                    return 200, {"data": [{"id": "270235042840463", "name": "Trendi"}, {"id": "999111222333", "name": "Other Page"}]}
                raise AssertionError(f"Unexpected Meta HTTP call: {method} {url}")

            monkeypatch.setattr(social.oauth, "_http_json", fake_biz_http)

            already = await client.post(
                "/owner/social/meta/businesses/link-page",
                headers=headers,
                json={"business_id": "801162021859410", "page_id": "270235042840463", "relation": "owned"},
            )
            assert already.status_code == 200, already.text
            assert already.json()["ok"] is True
            assert already.json()["access_status"] == "ALREADY_LINKED"
            assert "Page is linked to Trendi" in already.json()["message"]

            failed = await client.post(
                "/owner/social/meta/businesses/link-page",
                headers=headers,
                json={"business_id": "801162021859410", "page_id": "999111222333", "relation": "owned"},
            )
            assert failed.status_code == 400
            assert "Meta error (200): Permissions error" in failed.json()["detail"]

    run(_go)
