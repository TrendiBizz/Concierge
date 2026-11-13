"""Pull a person's details out of what they actually wrote.

Most enquiries never fill in a form. They say "hi it's Sarah from Acme, can you call me on
021 555 1234". Before this, that name, company and number were visible to the owner in the message
and invisible to the CRM: only the channel that carried the message was stored.

One extractor, used by every channel, so chat, SMS, email and social all capture the same details.

Every rule here is deliberately conservative. A wrong name pinned to a customer is worse than no
name, and a wrong number is worse than none, so a field is filled only when the text says it plainly.
"""
import re

from .contact import normalize_phone

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
_PHONE = re.compile(r"(?<![\d/])(?:\+\d{1,3}[\s-]?)?(?:\(?0\d{1,4}\)?[\s-]?)?"
                    r"\d{3,4}[\s-]?\d{3,4}(?![\d/])")

# "my name is Sarah", "I'm Sarah", "this is Sarah", "call me Sarah", "it's Sarah from Acme"
# The trigger words are matched in any case ("My name is", "my name is"), while the captured part
# stays case-sensitive so the word after it must actually look like a name.
_NAME = re.compile(
    r"\b(?i:my\s+name\s+is|i'?m|i\s+am|this\s+is|call\s+me|it'?s|name\s*:)\s+"
    r"([A-Z][a-z'’-]+(?:\s+[A-Z][a-z'’-]+){0,2})\b")
_COMPANY = re.compile(
    r"\b(?:from|at|with)\s+([A-Z][\w&.'’-]*(?:\s+[A-Z][\w&.'’-]*){0,3}"
    r"(?:\s+(?:Ltd|Limited|LLC|Inc|Group|Construction|Builders|Building|Plumbing|"
    r"Electrical|Design|Studio|Agency|Consulting|Services|Solutions)))\b")

_NOT_A_NAME = {
    "interested", "looking", "after", "sorry", "just", "having", "trying", "thinking", "wondering",
    "keen", "based", "working", "planning", "hoping", "writing", "following", "in", "on", "at",
    "the", "a", "an", "not", "sure", "new", "here", "good", "fine", "okay", "ok",
}


def _clean_name(value: str) -> str:
    words = value.strip().split()
    if not words or words[0].lower() in _NOT_A_NAME:
        return ""
    # A single capitalised word is only a name when the sentence says so ("my name is Sarah").
    return " ".join(words)[:80] if all(w[:1].isupper() for w in words) else ""


def extract_details(text: str, default_cc: str = "", *, allow_phone: bool = True) -> dict:
    """{'name','email','phone','company'} — each '' when the text does not plainly say it."""
    body = (text or "").replace("\r", "")
    found = {"name": "", "email": "", "phone": "", "company": ""}
    if not body.strip():
        return found

    match = _EMAIL.search(body)
    if match:
        found["email"] = match.group().rstrip(".,;:)]").lower()

    if allow_phone:
        for candidate in _PHONE.finditer(body):
            number = normalize_phone(candidate.group(), default_cc)
            if number:
                found["phone"] = number
                break

    match = _NAME.search(body)
    if match:
        found["name"] = _clean_name(match.group(1))
    if not found["name"]:
        # People sign text messages with their name on the last line: "Sarah".
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if lines:
            tail = lines[-1]
            if (len(tail.split()) <= 2 and 2 < len(tail) < 40 and "@" not in tail
                    and not any(ch.isdigit() for ch in tail)):
                found["name"] = _clean_name(tail)

    match = _COMPANY.search(body)
    if match:
        found["company"] = match.group(1)[:120]
    return found
