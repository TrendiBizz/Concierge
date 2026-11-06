"""Lead scoring: transparent, rule-based, 0-100, with weights each client can tune.

Every point comes from a stated reason, so the business owner can see why a lead is hot. There is no
model call and no randomness: the same lead and the same weights always give the same score. This is
deliberately not "AI" scoring, and the website must not describe it as AI.

Each client may override any weight (tenants.scoring, a JSON object of key -> number). Anything not
overridden uses DEFAULT_WEIGHTS. Labels: hot (hot_at or more), warm (warm_at or more), else cold.
"""

import json
import re

from . import db

# key -> (default, label shown in the dashboard, kind). kind: points | count | threshold
WEIGHTS: dict[str, tuple[int, str, str]] = {
    "phone": (25, "Gave a phone number", "points"),
    "email": (10, "Gave an email address", "points"),
    "name": (5, "Gave a name", "points"),
    "consent": (10, "Agreed to be contacted", "points"),
    "booked": (30, "Booked an appointment", "points"),
    "intent_each": (10, "Each price / booking / timing word (see cap)", "points"),
    "intent_cap": (2, "Most intent words that count", "count"),
    "long_message": (5, "Described what they need (40+ characters)", "points"),
    "voice_or_sms": (10, "Reached out by text or voice", "points"),
    "high_intent_page": (10, "Was on a pricing, booking or contact page", "points"),
    "conversation": (10, "Had a real conversation (3+ messages)", "points"),
    "spam_link": (-25, "Message contains a link (possible spam)", "points"),
    "hot_at": (70, "Score needed to be HOT", "threshold"),
    "warm_at": (40, "Score needed to be WARM", "threshold"),
}
DEFAULT_WEIGHTS = {key: spec[0] for key, spec in WEIGHTS.items()}
HOT_AT = DEFAULT_WEIGHTS["hot_at"]
WARM_AT = DEFAULT_WEIGHTS["warm_at"]

INTENT_RE = re.compile(
    r"\b(price|prices|pricing|cost|quote|quotation|how much|book|booking|appointment|available|"
    r"availability|today|tomorrow|this week|urgent|asap|emergency|buy|order|hire|start)\b",
    re.IGNORECASE,
)
HIGH_INTENT_PAGE_RE = re.compile(r"(pricing|price|quote|book|contact|checkout|order)", re.IGNORECASE)
LINK_RE = re.compile(r"https?://|www\.", re.IGNORECASE)


# ---- weights --------------------------------------------------------------------
def validate_overrides(raw) -> dict[str, int]:
    """Check a client's overrides. Raises ValueError with a plain message on anything unsafe."""
    if not isinstance(raw, dict):
        raise ValueError("scoring must be an object of weight overrides")
    clean: dict[str, int] = {}
    for key, value in raw.items():
        if key not in WEIGHTS:
            raise ValueError(f"unknown scoring key '{key}'")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"'{key}' must be a whole number")
        kind = WEIGHTS[key][2]
        low, high = {"points": (-50, 50), "count": (0, 5), "threshold": (1, 100)}[kind]
        if not low <= value <= high:
            raise ValueError(f"'{key}' must be between {low} and {high}")
        clean[key] = value
    merged = {**DEFAULT_WEIGHTS, **clean}
    if merged["warm_at"] >= merged["hot_at"]:
        raise ValueError("warm_at must be lower than hot_at")
    return clean


def effective_weights(overrides: dict | None) -> dict[str, int]:
    return {**DEFAULT_WEIGHTS, **(overrides or {})}


def weights_for(tenant: dict | None) -> dict[str, int]:
    """The weights in force for a client: defaults plus their overrides."""
    raw = (tenant or {}).get("scoring")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    return effective_weights(raw if isinstance(raw, dict) else {})


def describe(tenant: dict | None) -> list[dict]:
    """Everything the dashboard needs to show the weight editor."""
    current = weights_for(tenant)
    return [
        {"key": key, "label": label, "kind": kind, "default": default, "value": current[key]}
        for key, (default, label, kind) in WEIGHTS.items()
    ]


# ---- scoring --------------------------------------------------------------------
def label_for(score: int, hot_at: int = HOT_AT, warm_at: int = WARM_AT) -> str:
    if score >= hot_at:
        return "hot"
    if score >= warm_at:
        return "warm"
    return "cold"


def assess(lead: dict, user_turns: int = 0, booked: bool = False, weights: dict | None = None) -> dict:
    """Score one lead. `lead` is a row dict; `user_turns` is how many messages the visitor sent."""
    w = effective_weights(weights)
    points: list[tuple[int, str]] = []
    message = (lead.get("message") or "").strip()

    def add(key: str, applies: bool, amount: int | None = None) -> None:
        value = w[key] if amount is None else amount
        if applies and value != 0:
            points.append((value, WEIGHTS[key][1]))

    add("phone", bool((lead.get("phone") or "").strip()))
    add("email", bool((lead.get("email") or "").strip()))
    add("name", len((lead.get("name") or "").strip()) >= 2)
    add("consent", bool(lead.get("consent_contact")))

    if booked:
        add("booked", True)
    else:
        found = {m.lower() for m in INTENT_RE.findall(message)}
        counted = min(len(found), w["intent_cap"])
        if counted and w["intent_each"]:
            points.append((counted * w["intent_each"], "Asked about price, booking or timing"))
        add("long_message", len(message) >= 40)

    add("voice_or_sms", (lead.get("channel") or "") in ("sms", "voice"))
    add("high_intent_page", bool(HIGH_INTENT_PAGE_RE.search(lead.get("page_url") or "")))
    add("conversation", user_turns >= 3)
    add("spam_link", bool(LINK_RE.search(message)))

    score = max(0, min(100, sum(p for p, _ in points)))
    return {
        "score": score,
        "label": label_for(score, w["hot_at"], w["warm_at"]),
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


async def apply(lead: dict, booked: bool = False, weights: dict | None = None) -> dict:
    """Score a saved lead, store the result on its row and return the lead dict with score fields."""
    turns = 0
    if lead.get("conversation_id"):
        turns = int(await db.pool().fetchval(
            "SELECT count(*) FROM messages WHERE conversation_id = $1 AND role = 'user'",
            lead["conversation_id"],
        ) or 0)
    result = assess(lead, turns, booked, weights)
    row = await db.pool().fetchrow(
        "UPDATE leads SET score = $2, score_label = $3, score_reasons = $4::jsonb, scored_at = now() "
        "WHERE id = $1 RETURNING *",
        lead["id"], result["score"], result["label"], json.dumps(result["reasons"]),
    )
    if row is not None:
        return dict(row)
    return {**lead, "score": result["score"], "score_label": result["label"], "score_reasons": result["reasons"]}


async def rescore_tenant(tenant: dict) -> dict:
    """Recompute every lead's score for a client with their current weights."""
    weights = weights_for(tenant)
    rows = await db.pool().fetch(
        """
        SELECT l.*,
               COALESCE((SELECT count(*) FROM messages m
                         WHERE m.conversation_id = l.conversation_id AND m.role = 'user'), 0) AS turns,
               EXISTS (SELECT 1 FROM appointments a
                       WHERE a.lead_id = l.id AND a.status <> 'cancelled') AS has_appointment
        FROM leads l WHERE l.tenant_id = $1
        """,
        tenant["id"],
    )
    updates, counts = [], {"hot": 0, "warm": 0, "cold": 0}
    for row in rows:
        lead = dict(row)
        result = assess(lead, int(lead["turns"]), bool(lead["has_appointment"]), weights)
        counts[result["label"]] += 1
        updates.append((lead["id"], result["score"], result["label"], json.dumps(result["reasons"])))
    if updates:
        async with db.pool().acquire() as conn:
            await conn.executemany(
                "UPDATE leads SET score = $2, score_label = $3, score_reasons = $4::jsonb, scored_at = now() "
                "WHERE id = $1",
                updates,
            )
    return {"rescored": len(updates), **counts}
