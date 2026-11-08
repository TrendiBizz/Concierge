"""Deliver only owner-approved Facebook/Instagram jobs in the isolated Meta review tenant.

The regular social scheduler remains disabled. Install/enable the accompanying
service only after the operator authorizes Meta reviewer access. Rust performs
all approval, revision, tenant, credential and idempotency checks at delivery.
"""
import json
import sqlite3
import subprocess
import time

CUSTOMER = "trendi-meta-review"
DATABASE = "/var/lib/docker/volumes/trendi_social/_data/social.db"


def select_due(connection, now):
    selected = []
    rows = connection.execute(
        "SELECT id,body,status,revision,approved_revision,scheduled_at FROM posts "
        "WHERE customer_id=? AND status IN ('scheduled','processing') "
        "AND scheduled_at<=? AND revision=approved_revision ORDER BY scheduled_at,id LIMIT 100",
        (CUSTOMER, now),
    )
    for post_id, body, *_ in rows:
        post = json.loads(body)
        accounts = post.get("account_ids", [])
        if post.get("customer_id") != CUSTOMER or len(accounts) != 1:
            continue
        account = connection.execute(
            "SELECT network FROM accounts WHERE customer_id=? AND id=? AND needs_reauth=0",
            (CUSTOMER, accounts[0]),
        ).fetchone()
        if account and account[0] in ("facebook", "instagram"):
            selected.append(post_id)
        if len(selected) == 4:
            break
    return selected


def main():
    with sqlite3.connect("file:" + DATABASE + "?mode=ro", uri=True) as connection:
        selected = select_due(connection, int(time.time()))
    for post_id in selected:
        result = subprocess.run([
            "docker", "run", "--rm", "--env-file", "/opt/trendi/shared/social.env",
            "-e", "SOCIAL_ENABLE_PUBLISH=true", "-e", "SOCIAL_DB=/data/social.db",
            "-e", "SOCIAL_MEDIA_DIR=/data/media", "-e",
            "SOCIAL_PUBLIC_MEDIA_BASE=https://concierge.trendibizz.com/api/v1/social-media",
            "-v", "trendi_social:/data", "--entrypoint", "/usr/local/bin/publish-reviewed-post",
            "trendi-concierge-social:vps", CUSTOMER, post_id,
        ], timeout=180, check=False)
        print("Meta review delivery:", post_id, "exit:", result.returncode, flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
