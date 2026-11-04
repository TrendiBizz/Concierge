import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_email(value: str) -> bool:
    return bool(value and EMAIL_RE.match(value.strip()))


def normalize_phone(raw: str, default_cc: str = "1") -> str | None:
    """Return an E.164 number (+15551234567) or None if it cannot be a real phone number."""
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if raw.startswith("+"):
        return "+" + digits if 8 <= len(digits) <= 15 else None
    if len(digits) == 10:
        return f"+{default_cc}{digits}"
    if len(digits) == 11 and digits.startswith(default_cc):
        return "+" + digits
    if 8 <= len(digits) <= 15:
        return "+" + digits
    return None


def contact_key(value: str, default_cc: str = "1") -> str:
    """Canonical key used for opt-out lookups: E.164 phone or lower-cased email."""
    value = (value or "").strip()
    if "@" in value:
        return value.lower()
    return normalize_phone(value, default_cc) or value
