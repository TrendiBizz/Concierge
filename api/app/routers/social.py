"""Owner social media and OAuth routes.

Moved out of app/main.py unchanged; paths and behaviour are identical. main.py re-exports the
handlers and request models so existing imports (tests, tooling) keep working.
"""
import sys

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import owner_auth, social_bridge

router = APIRouter()


def _main():
    return sys.modules[__package__.rsplit(".", 1)[0] + ".main"]


# The portal is the identity and approval interface; the Rust service never
# receives a customer browser's auth token, and no social secrets reach the UI.


@router.get("/owner/social/oauth/callback", include_in_schema=False)
async def owner_social_oauth_callback():
    # Public landing page only. It cannot exchange a code or authenticate anyone.
    # The original logged-in tab compares state before exchanging the code itself.
    from ..security import html_with_script_nonce

    return html_with_script_nonce(
        (_main().STATIC_DIR / "social-oauth-callback.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate",
                 "Pragma": "no-cache", "Referrer-Policy": "no-referrer",
                 "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY"},
    )


class OwnerSocialDraft(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    account_ids: list[str] = Field(min_length=1, max_length=10)
    link: str = Field(default="", max_length=2000)
    hashtags: str = Field(default="", max_length=2000)
    media: list[str] = Field(default_factory=list, max_length=10)
    options: dict = Field(default_factory=dict)


class OwnerSocialCompose(OwnerSocialDraft):
    video: str | None = Field(default=None, max_length=2048)


@router.post("/owner/social/media")
async def owner_social_media_upload(request: Request, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    from .. import social as social_mod

    slug = await social_bridge.ensure_tenant(user)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 64 * 1024 * 1024:
            raise HTTPException(413, "Upload a file smaller than 64 MB")
    return await social_mod.media.save_media(slug, bytes(content))


@router.get("/api/v1/social-media/{token}")
async def social_media_download(token: str):
    from .. import social as social_mod

    mime, data = await social_mod.media.resolve_download_token(token)
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex, nofollow"},
    )


@router.post("/owner/social/compose")
async def owner_social_compose(body: OwnerSocialCompose,
                               user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    return await social_bridge.compose(user, body.model_dump())


class OwnerSocialSchedule(BaseModel):
    scheduled_at: int = Field(ge=0)


@router.get("/owner/social/status")
async def owner_social_status(user: dict = Depends(owner_auth.current_user)):
    # No credentials, client IDs, access tokens or internal hostnames in the response.
    from .. import social as social_mod

    enabled = social_mod.config.is_social_enabled()
    providers = {"linkedin_organization": False, "linkedin": False, "facebook": False, "instagram": False, "google_business": False, "tiktok": False, "x": False}
    publish_enabled = {name: False for name in providers}
    if enabled:
        try:
            status = await social_bridge.provider_status()
            providers = {name: status.get(name) is True for name in providers}
            publish_enabled = social_mod.config.publish_status()
        except HTTPException:
            pass
    live_pub = social_mod.config.is_live_publishing_enabled()
    return {"enabled": enabled,
            "customer": user["slug"],
            "providers": providers,
            "publish_enabled": publish_enabled,
            "callback_path": "/owner/social/oauth/callback",
            "live_publishing": live_pub}


@router.post("/owner/social/oauth/renew/{account_id}")
async def owner_social_oauth_renew(account_id: str,
                                  user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.renew_social_token(user, account_id)


class OwnerOAuthCallback(BaseModel):
    state: str = Field(min_length=32, max_length=256)
    code: str = Field(min_length=1, max_length=2048)


@router.post("/owner/social/oauth/tiktok/start")
async def owner_social_tiktok_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.start_tiktok_oauth(user)


@router.post("/owner/social/oauth/tiktok/finish")
async def owner_social_tiktok_finish(body: OwnerOAuthCallback,
                                     user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.finish_tiktok_oauth(user, body.state, body.code)


@router.delete("/owner/social/oauth/tiktok/accounts/{account_id}")
async def owner_social_tiktok_disconnect(account_id: str,
                                         user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.disconnect_tiktok(user, account_id)


@router.post("/owner/social/oauth/google/start")
async def owner_social_google_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.start_google_oauth(user)


@router.post("/owner/social/oauth/google/finish")
async def owner_social_google_finish(body: OwnerOAuthCallback,
                                     user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.finish_google_oauth(user, body.state, body.code)


@router.delete("/owner/social/oauth/google/accounts/{account_id}")
async def owner_social_google_disconnect(account_id: str,
                                          user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.disconnect_google(user, account_id)


@router.post("/owner/social/oauth/x/start")
async def owner_social_x_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.start_x_oauth(user)


@router.post("/owner/social/oauth/x/finish")
async def owner_social_x_finish(body: OwnerOAuthCallback,
                                     user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.finish_x_oauth(user, body.state, body.code)


@router.delete("/owner/social/oauth/x/accounts/{account_id}")
async def owner_social_x_disconnect(account_id: str,
                                          user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.disconnect_x(user, account_id)


@router.post("/owner/social/oauth/meta/{network}/start")
async def owner_social_meta_start(network: str,
                                  user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if network not in ("facebook", "instagram"):
        raise HTTPException(404, "Unsupported social network")
    return await social_bridge.start_meta_oauth(user, network)


@router.post("/owner/social/oauth/meta/{network}/finish")
async def owner_social_meta_finish(network: str, body: OwnerOAuthCallback,
                                   user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if network not in ("facebook", "instagram"):
        raise HTTPException(404, "Unsupported social network")
    result = await social_bridge.finish_meta_oauth(user, network, body.state, body.code)
    # Persist Page / IG business IDs and encrypted Page tokens for inbound/outbound Meta messaging,
    # and strip access tokens before returning anything to the browser.
    channels = result.pop("channels", None) if isinstance(result, dict) else None
    if channels:
        from .. import meta_inbound
        await meta_inbound.sync_social_meta_channels(user["tenant_id"], channels)
    return result


@router.delete("/owner/social/oauth/meta/{network}/accounts/{account_id}")
async def owner_social_meta_disconnect(network: str, account_id: str,
                                       user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if network not in ("facebook", "instagram"):
        raise HTTPException(404, "Unsupported social network")
    from .. import meta_inbound
    await meta_inbound.unsubscribe_and_remove_social_channels(user["tenant_id"], network, account_id)
    return await social_bridge.unlink_meta(user, network, account_id)


@router.delete("/owner/social/oauth/linkedin/accounts/{account_id}")
async def owner_social_linkedin_unlink(
    account_id: str, user: dict = Depends(owner_auth.current_user)
):
    owner_auth.require_role(user, "owner")
    return await social_bridge.unlink_linkedin(user, account_id)


@router.post("/owner/social/oauth/linkedin_organization/start")
async def owner_social_linkedin_organization_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.start_linkedin_organization_oauth(user)


@router.post("/owner/social/oauth/linkedin_organization/finish")
async def owner_social_linkedin_organization_finish(body: OwnerOAuthCallback, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.finish_linkedin_organization_oauth(user, body.state, body.code)


@router.post("/owner/social/oauth/linkedin/start")
async def owner_social_linkedin_start(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.start_linkedin_oauth(user)


@router.post("/owner/social/oauth/linkedin/finish")
async def owner_social_linkedin_finish(body: OwnerOAuthCallback,
                                       user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.finish_linkedin_oauth(user, body.state, body.code)


@router.get("/owner/social/accounts")
async def owner_social_accounts(user: dict = Depends(owner_auth.current_user)):
    return await social_bridge.accounts(user)


@router.get("/owner/social/posts")
async def owner_social_posts(user: dict = Depends(owner_auth.current_user)):
    return await social_bridge.posts(user)


@router.post("/owner/social/posts")
async def owner_social_create(body: OwnerSocialDraft,
                              user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    return await social_bridge.create_draft(user, body.content, body.account_ids,
                                            body.link, body.hashtags, body.media, body.options)


@router.post("/owner/social/posts/{post_id}/submit")
async def owner_social_submit(post_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    return await social_bridge.submit_draft(user, post_id)


@router.post("/owner/social/posts/{post_id}/approval-request")
async def owner_social_request_approval(post_id: str, body: OwnerSocialSchedule,
                                        user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.request_approval(user, post_id, body.scheduled_at)


@router.post("/owner/social/approvals/{token}/approve")
async def owner_social_approve(token: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.decide(user, token, True)


@router.post("/owner/social/approvals/{token}/reject")
async def owner_social_reject(token: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await social_bridge.decide(user, token, False)


@router.post("/owner/social/posts/{post_id}/dry-run")
async def owner_social_dry_run(post_id: str, user: dict = Depends(owner_auth.current_user)):
    """Validate guardrails, account credentials, and exact network payloads without posting."""
    owner_auth.require_role(user, "editor")
    from .. import social as social_mod

    if not social_bridge.POST_ID.fullmatch(post_id):
        raise HTTPException(400, "Invalid post identifier")
    slug = await social_bridge.ensure_tenant(user)
    posts = await social_mod.store.list_posts(slug, limit=200)
    post = next((p for p in posts if p["id"] == post_id), None)
    if not post:
        raise HTTPException(404, "Social post not found")
    results = []
    for aid in post["account_ids"]:
        acct = await social_mod.store.get_account_credentials(slug, aid, allow_expired=False)
        outcome = await social_mod.publishers.publish_to_account(
            customer_slug=slug, post=post, account=acct, dry_run=True
        )
        results.append({
            "account_id": aid,
            "network": acct["network"],
            "ok": outcome.ok,
            "error": outcome.error,
            "payload": outcome.dry_run_payload,
        })
    return {"post_id": post_id, "dry_run": True, "results": results}
