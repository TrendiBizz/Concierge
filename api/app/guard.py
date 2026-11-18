"""Quote-guard: the assistant must never state a dollar price that is not backed by evidence.

A reply is allowed to contain a $ amount only if that amount appears in the website
information retrieved for the turn, in tool results, or in the tenant's own persona/offer
text. Amounts the visitor typed do not count, so the assistant cannot be talked into
confirming a price the business never published. Anything else is treated as an invented price.

Limitation: this checks text replies (web chat, SMS). It cannot intercept spoken voice
replies - for voice we rely on the prompt and the search_knowledge tool.
"""

import re
from decimal import Decimal

_NUM = r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?\s?(k\b)?"
# "$500", "NZ$500", "NZD 500", "$5k" and "500 dollars" / "500 NZD" / "500 bucks" all state a price.
AMOUNT_RE = re.compile(
    r"(?:\$|\b(?:NZD|USD|AUD)\s?)\s?" + _NUM + r"|" + _NUM + r"\s?(?:dollars?|bucks|NZD|USD|AUD)\b",
    re.IGNORECASE)

FALLBACK = (
    "I don't have exact pricing on hand, and I don't want to guess. I can have the team "
    "confirm it for you - could I take your name and a phone number or email?"
)

CORRECTION = (
    "Your previous answer contained a price that is not in the website information. Rewrite "
    "it without inventing any dollar amounts. If the exact price is not in the information, "
    "say you are not sure and offer to have the team confirm it (collect their contact details)."
)


def amounts(text: str) -> set[Decimal]:
    found: set[Decimal] = set()
    for match in AMOUNT_RE.finditer(text or ""):
        g = match.groups()
        whole, frac, kilo = next(g[i:i + 3] for i in (0, 3) if g[i])
        value = Decimal(f"{whole.replace(',', '')}.{frac or '0'}")
        found.add((value * 1000 if kilo else value).normalize())
    return found


def unknown_amounts(reply: str, evidence: str) -> set[Decimal]:
    return amounts(reply) - amounts(evidence)
