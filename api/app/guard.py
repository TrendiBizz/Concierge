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

AMOUNT_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?")

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
        whole = match.group(1).replace(",", "")
        frac = match.group(2) or "0"
        found.add(Decimal(f"{whole}.{frac}").normalize())
    return found


def unknown_amounts(reply: str, evidence: str) -> set[Decimal]:
    return amounts(reply) - amounts(evidence)
