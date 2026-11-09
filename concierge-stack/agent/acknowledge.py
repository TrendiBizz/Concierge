"""Builds the acknowledgement a caller gets after leaving a message.

The caller chooses three things, one at a time on the call:
  reply_channel    "text", "email" or "none"
  ack_style        "summary" (a short recap of what they asked about) or "short" (just that we
                   have their message)
  followup_method  how the team will follow up: "email" or "phone call"

Wording rules (same as the rest of the agent): never "free", no prices, no promises, no times,
no exclamation marks. A summary that breaks a rule is dropped and the short acknowledgement is
sent instead, so a model slip can never put a price or promise in a caller's phone.
"""
from __future__ import annotations

import re

CONTACT = "admin@trendibizz.com"
TEXT_LIMIT = 320  # two standard SMS segments

_FOLLOW = {"email": "by email", "phone call": "by phone call"}
_BANNED = re.compile(r"\bfree\b|\$|\busd\b|\bnzd\b|%|\bguarantee|\bpromise", re.IGNORECASE)


def normalize_channel(value: str) -> str:
    v = (value or "").strip().lower()
    if v in ("text", "sms", "text message"):
        return "text"
    if v in ("email", "e-mail"):
        return "email"
    return "none"


def normalize_style(value: str) -> str:
    return "summary" if (value or "").strip().lower() == "summary" else "short"


def normalize_followup(value: str) -> str:
    v = (value or "").strip().lower()
    if v == "email" or v == "e-mail":
        return "email"
    if v in ("phone", "phone call", "call", "a call", "phone-call"):
        return "phone call"
    return ""


def clean_summary(summary: str) -> str:
    """Return a safe one-line summary, or '' if it is empty or breaks a wording rule."""
    s = " ".join((summary or "").replace("!", ".").split())
    if not s or _BANNED.search(s):
        return ""
    if s[-1] not in ".?":
        s += "."
    return s


def build_ack(channel: str, style: str, summary: str, followup: str) -> str:
    """The acknowledgement text. `channel` only matters for the text-message length limit."""
    follow = (
        f"A member of the Trendi team will follow up {_FOLLOW[followup]}."
        if followup in _FOLLOW
        else "A member of the Trendi team will follow up."
    )
    tail = f" {follow} Questions: {CONTACT}"
    short = f"Trendi: we have your message.{tail}"
    s = clean_summary(summary) if style == "summary" else ""
    if not s:
        return short
    head = "Trendi: we have your message about: "
    body = f"{head}{s}{tail}"
    if channel == "text" and len(body) > TEXT_LIMIT:
        room = TEXT_LIMIT - len(head) - len(tail) - 3
        if room < 30:
            return short
        cut = s[:room].rsplit(" ", 1)[0].rstrip(" ,.;:")
        body = f"{head}{cut}...{tail}"
    return body
