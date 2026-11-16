"""Release versions and the notice customers get when the software changes.

Add a new entry to RELEASES and bump nothing else: CURRENT_VERSION follows the highest key. A person sees the notice
for the newest release they have not dismissed (tenant_users.last_seen_version), so nobody is shown the same notice
twice and nobody misses one. The owner can also be emailed once per release (announce), never twice.
"""
from . import db, outbox

RELEASES: dict[int, dict] = {
    1: {
        "released": "2026-11-17",
        "title": "Version 1",
        "summary": "The first numbered release of Trendi Concierge.",
        "notes": [
            "A 7am \"what needs you today\" email, if you switch it on in Business setup.",
            "Replies prepared for you appear under \"Needs you\" to approve, edit or discard. Nothing is sent to your customers until you approve it.",
            "Ask Concierge: a read-only box that answers questions about your business from the information you have added.",
        ],
    },
}
CURRENT_VERSION = max(RELEASES)


def label(version: int = CURRENT_VERSION) -> str:
    return RELEASES[version]["title"]


def notice(last_seen: int) -> dict:
    """What a person with this last_seen_version should be shown."""
    cur = RELEASES[CURRENT_VERSION]
    return {"version": CURRENT_VERSION, "label": cur["title"], "released": cur["released"],
            "summary": cur["summary"], "notes": cur["notes"], "unseen": last_seen < CURRENT_VERSION}


async def mark_seen(user_id, version: int = CURRENT_VERSION) -> None:
    await db.pool().execute(
        "UPDATE tenant_users SET last_seen_version = GREATEST(last_seen_version, $2) WHERE id = $1",
        user_id, min(version, CURRENT_VERSION))


def announcement(tenant_name: str, version: int = CURRENT_VERSION) -> tuple[str, str]:
    r = RELEASES[version]
    lines = [f"Hello. Trendi Concierge has been updated to {r['title']}.", "", r["summary"], ""]
    lines += [f"- {n}" for n in r["notes"]]
    lines += ["", f"Sign in to Studio to see it: https://concierge.trendibizz.com/studio/",
              f"This note is about {tenant_name}'s account. Nothing about your customers' messages has changed."]
    return f"Trendi Concierge {r['title']}: what's new", "\n".join(lines) + "\n"


async def announce(version: int = CURRENT_VERSION, dry_run: bool = True) -> dict:
    """Email every active business's notification address once about this release."""
    if version not in RELEASES:
        raise ValueError("Unknown version")
    rows = await db.pool().fetch(
        "SELECT id, name, notify_email FROM tenants WHERE notify_email IS NOT NULL AND notify_email <> '' ORDER BY name")
    recipients, queued = [], 0
    for t in rows:
        recipients.append({"tenant": t["name"], "to": t["notify_email"]})
        if dry_run:
            continue
        subject, body = announcement(t["name"], version)
        if await outbox.enqueue(t["id"], "owner_alert", "email", t["notify_email"], body, subject=subject,
                                dedupe_key=f"release:{version}:{t['id']}"):
            queued += 1
    return {"version": version, "dry_run": dry_run, "recipients": recipients, "queued": queued}
