"""Server-owned A2UI v0.8 catalog. No executable UI or arbitrary tools from visitors."""
import re
from datetime import datetime
from uuid import uuid4

PRICING_TENANTS = {"trendi-oauth-staging", "trendi", "trendibizz", "trendi-concierge", "concierge"}
FIELDS = {
    "quote": {"email": "Email (required)", "details": "What do you need? (required)"},
    "booking": {"email": "Email (required)", "when": "Preferred date and time (required)", "timezone": "Time zone, e.g. Pacific/Auckland (required)"},
    "contact": {"email": "Email (required)", "details": "Message (required)"},
    "pricing": {}, "confirmation": {},
}
TITLES = {"quote": "Request a quote", "booking": "Request a booking", "contact": "Contact the team",
          "pricing": "Concierge pricing", "confirmation": "Request received"}
TEXT = {"quote": "Tell us what you need. The team will prepare a quote.",
        "booking": "Choose a preferred time and time zone. This is a request; no slot is reserved.",
        "contact": "Leave your details for the team to follow up.",
        "pricing": "Concierge: USD $199/month. 3-month minimum. Prices are in USD. No payment is taken here.",
        "confirmation": "Your request was saved for the team. A booking or delivery is not confirmed."}
BUTTONS = {"quote": "Send quote request", "booking": "Send booking request", "contact": "Send contact details",
           "pricing": "Ask about this plan", "confirmation": "Acknowledge"}


def choose(message: str, tenant: dict) -> str | None:
    text = message.lower()
    if re.search(r"\b(quote|quotation)\b", text):
        return "quote"
    if re.search(r"\b(book|booking|appointment|schedule)\b", text):
        return "booking"
    if re.search(r"\b(contact|callback|call back)\b", text):
        return "contact"
    # This is the Trendi Concierge offer, never a price for another tenant's business.
    if tenant.get("slug") in PRICING_TENANTS and re.search(r"\b(price|pricing|cost|plan)\b", text):
        return "pricing"
    return None


def card(kind: str) -> list[dict]:
    sid = "cc-" + kind + "-" + uuid4().hex
    def component(cid, name, props):
        return {"id": cid, "component": {name: props}}
    def literal(value):
        return {"literalString": value}
    parts = [component("title", "Text", {"text": literal(TITLES[kind]), "usageHint": "h3"}),
             component("description", "Text", {"text": literal(TEXT[kind])})]
    for key, label in FIELDS[kind].items():
        if key == "when":
            parts.append(component(key, "DateTimeInput", {"value": {"path": "/when"}, "enableDate": True, "enableTime": True}))
        else:
            parts.append(component(key, "TextField", {"label": literal(label), "text": {"path": "/" + key}}))
    parts += [component("button-label", "Text", {"text": literal(BUTTONS[kind])}),
              component("submit", "Button", {"child": "button-label", "primary": True,
                  "action": {"name": "submit_" + kind, "context": [
                      {"key": key, "value": {"path": "/" + key}} for key in FIELDS[kind]]}}),
              component("column", "Column", {"children": {"explicitList": ["title", "description", *FIELDS[kind], "submit"]}}),
              component("root", "Card", {"child": "column"})]
    return [{"surfaceUpdate": {"surfaceId": sid, "components": parts}},
            {"dataModelUpdate": {"surfaceId": sid, "contents": [
                {"key": key, "valueString": ""} for key in FIELDS[kind]]}},
            {"beginRendering": {"surfaceId": sid, "root": "root"}}]


def validate_action(action: dict) -> tuple[str, dict]:
    kind = action["name"].removeprefix("submit_")
    if kind not in FIELDS or action["name"] != "submit_" + kind:
        raise ValueError("Unsupported action")
    if not re.fullmatch(r"cc-" + kind + r"-[a-f0-9]{32}", action["surfaceId"]) or action["sourceComponentId"] != "submit":
        raise ValueError("Invalid surface or source")
    if set(action["context"]) != set(FIELDS[kind]):
        raise ValueError("Unexpected fields")
    values = {}
    for key, value in action["context"].items():
        if not isinstance(value, str) or not value.strip() or len(value) > 1000:
            raise ValueError("Complete all required fields (maximum 1000 characters)")
        values[key] = value.strip()
    if "email" in values and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values["email"]):
        raise ValueError("Enter a valid email")
    if "when" in values:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            zone = ZoneInfo(values["timezone"])
            when = datetime.fromisoformat(values["when"])
            if when.tzinfo is not None or when.replace(tzinfo=zone) <= datetime.now(zone):
                raise ValueError("Choose a future local time")
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Choose a future date and a valid IANA time zone") from None
    return kind, values
