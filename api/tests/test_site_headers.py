"""The site's security headers must be valid, as served.

Audit 2026-11-16: `_headers` shipped `script-src ... 'nonce-{CSP_NONCE}'`, a template placeholder
nothing ever filled. Chrome logged "invalid source ... It will be ignored" on every page, and the
fixed public string protected nothing.
"""

import pathlib

HEADERS = pathlib.Path(__file__).resolve().parents[2] / "website" / "_headers"


def test_no_header_carries_an_unfilled_template_placeholder():
    for line in HEADERS.read_text().splitlines():
        assert "{" not in line and "}" not in line, f"placeholder left in a header: {line.strip()[:80]}"


def test_scripts_are_not_opened_up_to_inline_code():
    csp = next(line for line in HEADERS.read_text().splitlines() if "Content-Security-Policy" in line)
    script = next(part for part in csp.split(";") if part.strip().startswith("script-src"))
    assert "unsafe-inline" not in script and "unsafe-eval" not in script and "nonce-" not in script
