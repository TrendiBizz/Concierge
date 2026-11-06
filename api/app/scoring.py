"""Lead scoring: transparent, rule-based, 0-100.

Every point comes from a stated reason, so the business owner can see why a lead is hot. There is no
model call and no randomness: the same lead always scores the same. This is deliberately not "AI"
scoring, and the website must not describe it as AI.

Labels: hot (70+), warm (40-69), cold (below 40).
"""

import json
import re

from . import db

HOT_AT = 70
WARM_AT = 40

INTENT_RE = re.compile(
    r"\b(price|prices|pricing|cost|quote|quotation|how much|book|booking|appointment|available|"
    r"availability|today|tomorrow|this week|urgent|asap|emergency|buy|order|hire|start)\b",
    re.IGNORECASE,
)
HIGH_INTENT_PAGE_RE = re.compile(r"(pricing|price|quote|book|contact|checkout|order)", re.IGNORECASE)
LINK_RE = re.compile(r"https?://|www\.", re.IGNORECASE)


def label_for(score: int) -> str:
    if score >= HOT_AT:
        return "hot"
    if score >= WARM_AT:
        return "warm"
    return "cold"


def assess(lead: dict, user_turns: int = 0, booked: bool = False) -> dict:
    """Score one lead. `lead` is a row dict; `user_turns` is how many messages the visitor sent."""
    points: list[tuple[int, str]] = []
    message = (lead.get("message") or "").strip()

    if (lead.get("phone") or "").strip():
        points.append((25, "Gave a phone number"))
    if (lead.get("email") or "").strip():
        points.append((10, "Gave an email address"))
    if len((lead.get("name") or "").strip()) >= 2:
        points.append((5, "Gave a name"))
    if lead.get("consent_contact"):
        points.append((10, "Agreed to be contacted"))

    if booked:
        points.append((30, "Booked an appointment"))
    else:
        found = {m.lower() for m in INTENT_RE.findall(message)}
        if found:
            points.append((min(len(found), 2) * 10, "Asked about price, booking or timing"))
        if len(message) >= 40:
            points.append((5, "Described what they need"))

    if (lead.get("channel") or "") in ("sms", "voice"):
        points.append((10, "Reached out by text or voice"))
    if HIGH_INTENT_PAGE_RE.search(lead.get("page_url") or ""):
        points.append((10, "Was on a pricing, booking or contact page"))
    if user_turns >= 3:
        points.append((10, "Had a real conversation (3 or more messages)"))
    if LINK_RE.search(message):
        points.append((-25, "Message contains a link (possible spam)"))

    score = max(0, min(100, sum(p for p, _ in points)))
    return {
        "score": score,
        "label": label_for(score),
        "reasons": [f"{'+' if p > 0 else ''}{p} {why}" for p, why in points],
    }


def reasons_of(lead: dict) -> list[str]:
    """score_reasons comes back from the database as a JSON string or a list."""
    raw = lead.get("score_reasons")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return list(raw) if isinstance(raw, list) else []


async def apply(lead: dict, booked: bool = False) -> dict:
    """Score a saved lead, store the result on its row and return the lead dict with score fields."""
    turns = 0
    if lead.get("conversation_id"):
        turns = int(await db.pool().fetchval(
            "SELECT count(*) FROM messages WHERE conversation_id = $1 AND role = 'user'",
            lead["conversation_id"],
        ) or 0)
    result = assess(lead, turns, booked)
    row = await db.pool().fetchrow(
        "UPDATE leads SET score = $2, score_label = $3, score_reasons = $4::jsonb, scored_at = now() "
        "WHERE id = $1 RETURNING *",
        lead["id"], result["score"], result["label"], json.dumps(result["reasons"]),
    )
    if row is not None:
        return dict(row)
    return {**lead, "score": result["score"], "score_label": result["label"], "score_reasons": result["reasons"]}
