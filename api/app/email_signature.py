"""Read the sender's name, company and phone out of an email signature.

The owner asked why a real enquiry sat in the CRM with no name. The answer was that the name was
sitting in the customer's own signature all along -- "Best regards, Conrad Schiess, Pukeko
Construction" -- and nothing ever read it.

This is deliberately conservative. A signature is guessed from weak evidence, so every field is
returned only when it is clearly there; a blank is better than a wrong name on a customer record.
"""
import re

# Lines that end the message and begin the signature block.
_CLOSING = re.compile(
    r"^(?:best\s+(?:regards|wishes)|kind\s+regards|warm\s+regards|regards|cheers|thanks|"
    r"thank\s+you|many\s+thanks|nga\s+mihi|ngā\s+mihi|ka\s+kitea|sincerely|yours\s+(?:truly|sincerely)"
    r")\s*[,!.]?$", re.I | re.M)
# Everything from here down is quoted history, a device footer, or a legal disclaimer.
_STOPS = re.compile(
    r"^(?:--\s*$|sent\s+from\b|sent\s+via\b|on\s+\w{3},\s|from:\s|to:\s|subject:\s|>|"
    r"this\s+email\s+and\s+any|confidential|disclaimer)", re.I)

_PHONE = re.compile(r"(?<![\d/])(?:\+\d{1,3}[\s-]?)?(?:\(?0\d{1,4}\)?[\s-]?)"
                    r"\d{3,4}[\s-]?\d{3,4}(?![\d/])")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_COMPANY_HINT = re.compile(
    r"\b(?:ltd|limited|llc|inc|group|construction|builders?|building|plumbing|electrical|"
    r"design|studio|agency|consulting|consultants|services|solutions|nz|co\.?)\b", re.I)


def _lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines()]


def _signature_block(text: str) -> list[str]:
    """The few lines under the closing word, or under a blank line near the end."""
    lines = _lines(text)
    for index in range(len(lines) - 1, -1, -1):
        if _CLOSING.match(lines[index]):
            block = []
            for line in lines[index + 1:]:
                if _STOPS.match(line):
                    break
                block.append(line)
            return block[:6]
    return []


def _looks_like_name(line: str) -> bool:
    if not line or "@" in line or any(ch.isdigit() for ch in line) or len(line) > 60:
        return False
    words = line.replace(",", "").split()
    if not 2 <= len(words) <= 4:
        return False
    if _COMPANY_HINT.search(line):
        return False
    # Every word starts with a capital: "Conrad Schiess", not "Best regards".
    return all(word[:1].isupper() for word in words)


def parse_signature(text: str) -> dict:
    """{'name', 'company', 'phone'} -- each '' when not confidently present."""
    block = _signature_block(text)
    found = {"name": "", "company": "", "phone": ""}
    for line in block:
        if not found["phone"]:
            phone = _PHONE.search(line)
            if phone and not _EMAIL.search(line[:phone.start()] or ""):
                # A number glued to an address line is a reference, not a phone.
                found["phone"] = phone.group().strip()
        if "@" in line:
            continue
        if not found["name"] and _looks_like_name(line):
            found["name"] = line
            continue
        if not found["company"] and line and not found["phone"] == line:
            if _COMPANY_HINT.search(line) or (found["name"] and 1 <= len(line.split()) <= 5):
                found["company"] = line
    if found["company"] and found["company"] == found["name"]:
        found["company"] = ""
    return found
