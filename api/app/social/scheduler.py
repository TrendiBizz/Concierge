"""Background scheduler for approved Concierge Social posts.

- Quarantines any posts left in `publishing` state on startup (never blindly duplicates).
- Checks `approved_revision == revision` immediately before publishing.
- Auto-refreshes expiring tokens prior to delivery.
- Records per-account outcomes in `social_post_results` and sets clear post statuses/errors.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from ..config import get_settings
from . import config as social_config
from . import guardrails, oauth, publishers, store

log = logging.getLogger("concierge.social.scheduler")

MAX_ATTEMPTS = 3


async def _ensure_fresh_token(customer_slug: str, account_id: str) -> dict:
    creds = await store.get_account_credentials(customer_slug, account_id, allow_expired=True)
    net = creds["network"]
    exp = creds["expires_at"]
    now = int(time.time())
    refreshable = net in ("linkedin", "linkedin_organization", "x", "tiktok", "google_business") or (
        net == "instagram" and social_config.instagram_login_mode() == "instagram"
    )
    lead_window = 300 if net == "x" else 7 * 86400
    if refreshable and exp and exp <= now + lead_window:
        await oauth.refresh_account_token(customer_slug, account_id, force=True)
        creds = await store.get_account_credentials(customer_slug, account_id, allow_expired=False)
    elif creds["needs_reauth"] or (exp and exp <= now):
        raise HTTPException(409, f"{net.replace('_', ' ').title()} account requires reconnection")
    return creds


async def run_due(*, dry_run: bool = False) -> int:
    if not dry_run and not social_config.is_live_publishing_enabled():
        return 0
    due_posts = await store.claim_due_posts()
    processed = 0
    for post in due_posts:
        processed += 1
        customer_slug = post["customer_id"]
        post_id = post["id"]

        if post["approved_revision"] != post["revision"]:
            await store.finish_post(
                customer_slug, post_id, "failed", last_error="Approved revision mismatch; re-approve this post"
            )
            continue

        account_ids = post["account_ids"]
        accounts_loaded: list[dict] = []
        load_err: str | None = None
        for aid in account_ids:
            try:
                creds = await _ensure_fresh_token(customer_slug, aid)
                accounts_loaded.append(creds)
            except HTTPException as exc:
                load_err = str(exc.detail)
                break
        if load_err:
            await store.finish_post(customer_slug, post_id, "failed", last_error=load_err)
            continue

        rules = await store.get_rules(customer_slug)
        chk = guardrails.check_post(
            content=post["content"],
            link=post["link"],
            hashtags=post["hashtags"],
            networks=[a["network"] for a in accounts_loaded],
            media_count=len(post["media"]),
            rules=rules,
        )
        if not chk["ok"]:
            msg = "; ".join(e["message"] for e in chk["errors"][:3])
            await store.finish_post(customer_slug, post_id, "failed", last_error=msg)
            continue

        errors: list[str] = []
        any_pending = False
        any_retryable = False
        max_retry_after = 60

        for acct in accounts_loaded:
            if await store.result_exists(post_id, acct["id"]):
                continue
            outcome = await publishers.publish_to_account(
                customer_slug=customer_slug, post=post, account=acct, dry_run=dry_run
            )
            if outcome.ok:
                await store.record_post_result(
                    post_id,
                    acct["id"],
                    ok=True,
                    external_post_id=outcome.external_post_id,
                    external_url=outcome.external_url,
                )
                if outcome.pending:
                    any_pending = True
            else:
                await store.record_post_result(post_id, acct["id"], ok=False, error=outcome.error)
                errors.append(outcome.error or f"{acct['network']} failed")
                if outcome.retryable:
                    any_retryable = True
                    max_retry_after = max(max_retry_after, outcome.retry_after_seconds or 60)

        if errors:
            if any_retryable and post["attempts"] < MAX_ATTEMPTS:
                next_at = datetime.now(timezone.utc) + timedelta(seconds=max_retry_after * post["attempts"])
                await store.finish_post(
                    customer_slug,
                    post_id,
                    "scheduled",
                    last_error="; ".join(errors)[:400],
                    reschedule_at=next_at,
                )
            else:
                await store.finish_post(customer_slug, post_id, "failed", last_error="; ".join(errors)[:400])
        elif any_pending:
            await store.finish_post(customer_slug, post_id, "processing")
        else:
            await store.finish_post(customer_slug, post_id, "published")
    return processed


async def publish_post_now(customer_slug: str, post_id: str) -> dict:
    """Owner-approved immediate synchronous publish returning live per-account results and URLs."""
    if not social_config.is_live_publishing_enabled():
        raise HTTPException(409, "Live publishing is currently paused on this server")

    post = await store.approve_and_claim_now(customer_slug, post_id)
    account_ids = post["account_ids"]
    accounts_loaded: list[dict] = []
    for aid in account_ids:
        try:
            creds = await _ensure_fresh_token(customer_slug, aid)
            accounts_loaded.append(creds)
        except HTTPException as exc:
            await store.finish_post(customer_slug, post_id, "failed", last_error=str(exc.detail))
            raise

    rules = await store.get_rules(customer_slug)
    chk = guardrails.check_post(
        content=post["content"],
        link=post["link"],
        hashtags=post["hashtags"],
        networks=[a["network"] for a in accounts_loaded],
        media_count=len(post["media"]),
        rules=rules,
    )
    if not chk["ok"]:
        msg = "; ".join(e["message"] for e in chk["errors"][:3])
        await store.finish_post(customer_slug, post_id, "failed", last_error=msg)
        raise HTTPException(400, msg or "Post failed guardrails")

    errors: list[str] = []
    any_pending = False
    for acct in accounts_loaded:
        if await store.result_exists(post_id, acct["id"]):
            continue
        outcome = await publishers.publish_to_account(
            customer_slug=customer_slug, post=post, account=acct, dry_run=False
        )
        if outcome.ok:
            await store.record_post_result(
                post_id,
                acct["id"],
                ok=True,
                external_post_id=outcome.external_post_id,
                external_url=outcome.external_url,
            )
            if outcome.pending:
                any_pending = True
        else:
            await store.record_post_result(post_id, acct["id"], ok=False, error=outcome.error)
            errors.append(outcome.error or f"{acct['network']} failed")

    if errors:
        await store.finish_post(customer_slug, post_id, "failed", last_error="; ".join(errors)[:400])
    elif any_pending:
        await store.finish_post(customer_slug, post_id, "processing")
    else:
        await store.finish_post(customer_slug, post_id, "published")

    updated = await store.get_post(customer_slug, post_id)
    return updated or post


async def run_forever(stop: asyncio.Event) -> None:
    try:
        quarantined = await store.quarantine_interrupted()
        if quarantined:
            log.warning("Quarantined %d interrupted social posts on startup", quarantined)
    except Exception:
        log.warning("Could not check for interrupted social posts on startup")

    while not stop.is_set():
        try:
            if social_config.is_live_publishing_enabled():
                await run_due()
        except Exception:
            log.exception("Social scheduler cycle failed")
        poll = max(5, int(getattr(get_settings(), "social_poll_seconds", 15) or 15))
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll)
        except asyncio.TimeoutError:
            pass
