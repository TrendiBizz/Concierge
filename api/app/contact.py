"""Contact identity: email validation and phone normalisation.

Phone normalisation decides which E.164 number we text, book against, unsubscribe and merge
customer identities on, so it is deliberately conservative: it only produces a number when the
input is unambiguously interpretable, and returns None otherwise. Returning None is always safer
than guessing, because a guess texts a stranger.

The four accepted input shapes are:

  1. International       +6421555123        -- explicit, used as-is
  2. National           021 555 123         -- trunk prefix stripped, country code applied
  3. Country code only   6421555123         -- country code applied, not duplicated
  4. Bare complete      2145550100          -- only where the country's national length is known

Anything else is refused. In particular a bare number that is SHORTER than the country's national
length is ambiguous once a trunk prefix could have been removed, so it is not guessed.
"""

import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# E.164 allows at most 15 digits, and no real subscriber number is shorter than 8.
MIN_E164_DIGITS = 8
MAX_E164_DIGITS = 15

# Per-country dialling facts. `trunk` is the national prefix that must be removed before the country
# code is applied; `national_lengths` are the significant-figure counts that identify a complete
# national number written WITHOUT a trunk prefix.
#
# Only countries listed here are interpreted beyond the international form. An unlisted country
# still accepts `+...` input (shape 1), which is unambiguous and needs no table entry.
DIAL_PLANS: dict[str, dict] = {
    "1":   {"trunk": "1", "national_lengths": (10,)},        # NANP: US, Canada
    "44":  {"trunk": "0", "national_lengths": (10,)},        # United Kingdom
    "61":  {"trunk": "0", "national_lengths": (9,)},         # Australia
    "64":  {"trunk": "0", "national_lengths": (8, 9)},       # New Zealand
    "353": {"trunk": "0", "national_lengths": (9,)},         # Ireland
    "49":  {"trunk": "0", "national_lengths": (10, 11)},     # Germany
    "33":  {"trunk": "0", "national_lengths": (9,)},         # France
    "91":  {"trunk": "0", "national_lengths": (10,)},        # India
}


def is_email(value: str) -> bool:
    return bool(value and EMAIL_RE.match(value.strip()))


def _digits(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def _valid_e164(digits: str) -> bool:
    return MIN_E164_DIGITS <= len(digits) <= MAX_E164_DIGITS


def normalize_phone(raw: str, default_cc: str = "1") -> str | None:
    """Return an E.164 number (+6421555123) or None when the input is not unambiguously one.

    None is a real answer, not a failure to try: it means "this is not a number I can safely dial".
    Callers must treat it as such rather than falling back to the raw string for sending.
    """
    raw = (raw or "").strip()
    cc = _digits(default_cc or "") or "1"

    if not raw:
        return None

    # A value with no digits at all is not a number in any format.
    digits = _digits(raw)
    if not digits:
        return None

    # Letters anywhere mean this is not a phone number; stripping them could fabricate one.
    # An explicit '+' is fine, and so are the usual separators.
    if re.search(r"[A-Za-z]", raw):
        return None

    # ---- shape 1: explicit international form. The '+' is authoritative.
    if raw.startswith("+"):
        return "+" + digits if _valid_e164(digits) else None

    plan = DIAL_PLANS.get(cc)
    if plan is None:
        # An unlisted country code: without a dial plan we cannot safely remove a trunk prefix or
        # judge completeness, so only an explicitly international number is accepted.
        return None

    trunk = plan["trunk"]
    national_lengths = plan["national_lengths"]

    # ---- shape 3: country code supplied, then the national number.
    # Strip it only when what remains is a valid national length, so we never eat a real digit.
    if digits.startswith(cc) and len(digits) > len(cc):
        rest = digits[len(cc):]
        # A leading trunk digit after the country code is redundant (e.g. 64 0 21 ... ).
        if trunk and rest.startswith(trunk) and len(rest) > 1:
            stripped = rest[len(trunk):]
            if len(stripped) in national_lengths:
                return "+" + cc + stripped
        if len(rest) in national_lengths:
            return "+" + cc + rest

    # ---- shape 2: national format with a trunk prefix.
    if trunk and digits.startswith(trunk) and len(digits) > 1:
        stripped = digits[len(trunk):]
        if len(stripped) in national_lengths:
            return "+" + cc + stripped
        return None

    # ---- shape 4: a complete national number written with no trunk prefix.
    if len(digits) in national_lengths:
        return "+" + cc + digits

    # Anything else is ambiguous. Refuse rather than guess.
    return None


def contact_key(value: str, default_cc: str = "1") -> str:
    """Canonical key used for opt-out and identity lookups: E.164 phone or lower-cased email.

    Falls back to the trimmed raw value when the input is not a usable phone number, because an
    opt-out must still be recordable for a contact we cannot parse -- refusing to store it would
    mean we could text someone who asked us to stop.
    """
    value = (value or "").strip()
    if "@" in value:
        return value.lower()
    return normalize_phone(value, default_cc) or value
