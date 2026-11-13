"""Read an HTML form post without requiring python-multipart.

`request.form()` asserts that `python-multipart` is installed — even for a plain
`application/x-www-form-urlencoded` body, which needs no multipart parser at all. It is not installed
in the image, so every form post raised, and callers that guarded with `except` silently fell back to
a default. That is how a customer's "pay 50% deposit" became a full-price invoice on 13 Nov, and why
the public privacy form returned a 500.
"""

from __future__ import annotations

from urllib.parse import parse_qs


async def read_form(request) -> dict[str, str]:
    """Return the posted fields as plain strings, whatever the encoding."""
    content_type = (request.headers.get("content-type") or "").lower()
    body = await request.body()
    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
            return {key: str(value) for key, value in form.items()}
        except AssertionError:  # no multipart parser available; treat as empty rather than 500
            return {}
    if not body:
        return {}
    parsed = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}
