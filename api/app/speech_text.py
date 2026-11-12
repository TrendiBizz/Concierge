"""Tidy spoken words for the messages people read (owner alerts, leads, text copies).

The stored transcript stays word-for-word, as the record of what was said. Only the copies that go out
are cleaned: filler sounds ("um", "uh", "er", "hm") and an immediate stutter on a short word ("I, I
would") add nothing for the reader. Numbers, email addresses and ordinary words are never touched, so
"umbrella", "errand" and "20 mm" are safe.
"""
import re

# A standalone filler sound with the commas/dots around it. "uh-huh" and words that merely start with
# these letters do not match because of the look-around.
_FILLER = re.compile(
    r"(?:[,;]\s*)?(?<![\w'-])(?:uhm+|uh+|um+|erm?|hm+)(?![\w'-])[\s,.!?…-]*",
    re.IGNORECASE,
)
# Only short function words are collapsed, so a real repeat ("had had", "that that") survives.
_STUTTER = re.compile(
    r"\b(i|a|the|to|and|we|my|it|is|can|you|so|but|if|in|on|at|for|of|me|our|your|would|could|i'd|i'm|i'll)"
    r"\b(?:,\s*|\s+)\1\b",
    re.IGNORECASE,
)
_MARK = "\x00"


def _drop_filler(match: re.Match) -> str:
    ends = re.findall(r"[.!?]", match.group(0))
    # A filler that carried the end of a sentence keeps that full stop; otherwise it leaves a marker so
    # the next word can be capitalised when the filler opened a sentence ("Uh, email." -> "Email.").
    return ends[-1] + " " if ends else " " + _MARK


def clean_speech(text: str | None) -> str:
    """Return `text` without filler sounds and stutters; empty if nothing else was said."""
    value = (text or "").strip()
    if not value:
        return ""
    value = _FILLER.sub(_drop_filler, value)
    for _ in range(3):
        collapsed = _STUTTER.sub(r"\1", value)
        if collapsed == value:
            break
        value = collapsed
    value = value.lstrip()
    value = re.sub(r"(^|[.!?]\s+)" + _MARK + r"\s*([a-z])",
                   lambda m: m.group(1) + m.group(2).upper(), value)
    value = value.replace(_MARK, "")
    value = re.sub(r"\s+([,.!?;:])", r"\1", value)
    value = re.sub(r"([.!?])(\s*[.!?])+", r"\1", value)
    value = re.sub(r"[,;]\s*([.!?])", r"\1", value)
    value = re.sub(r"\s{2,}", " ", value)
    value = re.sub(r"^[\s,;]+", "", value)
    value = re.sub(r"[,;]\s*$", ".", value)
    # Only punctuation left means nothing real was said.
    return value.strip() if re.search(r"\w", value) else ""
