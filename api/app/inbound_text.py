"""Turn whatever a mail provider handed us into readable text.

The Cloudflare Worker sends `text` from the MIME body. Its fallback for HTML-only mail strips
tags, but it leaves three things behind, and on 2026-11-15 all three reached a customer-facing
notification: the CSS inside `<style>` (`/* --- RESPONSIVE --- */ :root { color-scheme: ... }`),
quoted-printable escapes (`=C2=B7`, `=3D`, soft line breaks), and the resulting wall of blank
lines. An Ahrefs crawl alert arrived as several hundred lines of stylesheet.

Nothing here is allowed to be clever: mail is untrusted, so this only ever *removes* markup and
normalises whitespace. It never interprets the message and never adds words.
"""
from __future__ import annotations

import html
import quopri
import re

# Whole blocks whose *content* is markup, not a message. Removed with their innards.
_BLOCK = re.compile(r"<(style|script|head|title)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
# A <style>/<script> left open by a truncating provider: drop the rest of that block.
_OPEN_BLOCK = re.compile(r"<(style|script|head|title)\b[^>]*>.*\Z", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"</?[a-zA-Z][^<>]*>")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# Quoted-printable shown literally as a mail body (the Worker did not decode it).
_QP_ESCAPE = re.compile(r"=(?:3D|[A-F0-9]{2})")
_SOFT_BREAK = re.compile(r"=\r?\n")
# A CSS rule left after its tags were stripped: `selector {`, `prop: value;`.
_CSS_SELECTOR = re.compile(r"^[.#a-zA-Z@:*\[][^{}]*\{$")
_CSS_RULE = re.compile(r"^[a-zA-Z-]+\s*:\s*[^;{}]+;$")
_CSS_COMMENT = re.compile(r"^/\*.*\*/$")
# A stylesheet comment can span lines, and CSS comments are never part of a person's message.
_CSS_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
# A whole rule on one line, e.g. `table[class=body] h1 { font-size: 28px !important; }`.
_CSS_ONELINE = re.compile(r"^[^{}]{1,200}\{[^{}]*:[^{}]*\}$")
_SEVERAL_BLANKS = re.compile(r"\n{3,}")

LIMIT = 20000


def clean_inbound_text(raw: str, limit: int = LIMIT) -> str:
    """Readable text from a mail body, at most `limit` characters."""
    text = (raw or "").replace("\x00", "")
    if not text.strip():
        return ""
    if _SOFT_BREAK.search(text) or _QP_ESCAPE.search(text):
        # Only try quoted-printable when the escapes are actually there: decoding an ordinary
        # message that happens to contain "=" would corrupt it.
        try:
            text = quopri.decodestring(text.encode("utf-8", "replace")).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - a body we cannot decode is left as it came
            pass
    text = _CSS_COMMENT_BLOCK.sub(" ", text)
    text = _COMMENT.sub(" ", text)
    text = _BLOCK.sub(" ", text)
    text = _OPEN_BLOCK.sub(" ", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        # Stylesheet leftovers carry no meaning for a person reading an enquiry.
        if (_CSS_SELECTOR.match(stripped) or _CSS_RULE.match(stripped)
                or _CSS_COMMENT.match(stripped) or _CSS_ONELINE.match(stripped)):
            continue
        if stripped in ("}", "{", "/*", "*/", ";,"):
            continue
        kept.append(re.sub(r"[ \t]+", " ", stripped))
    return _SEVERAL_BLANKS.sub("\n\n", "\n".join(kept)).strip()[:limit]
