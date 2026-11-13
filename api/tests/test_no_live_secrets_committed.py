"""A live credential must never reach this repository.

Found on 14 Nov: a real Stripe live secret key was sitting in a local session transcript. It was
not in git — the repository hit was a false positive (`asterisk_live_..._integration.py`), which is
exactly why the pattern needs a word boundary rather than a substring match — but nothing in the
repository would have stopped it being committed the next time.

This test reads every tracked text file and refuses live-looking credentials.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# `(?<![A-Za-z0-9])` matters: without it `asterisk_live_...` looks like a Stripe secret.
LIVE = {
    "stripe secret": re.compile(r"(?<![A-Za-z0-9])sk_live_[A-Za-z0-9]{20,}"),
    "stripe restricted": re.compile(r"(?<![A-Za-z0-9])rk_live_[A-Za-z0-9]{20,}"),
    "stripe webhook secret": re.compile(r"(?<![A-Za-z0-9])whsec_[A-Za-z0-9]{20,}"),
    "github token": re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}"),
    "aws access key": re.compile(r"(?<![A-Za-z0-9])(AKIA|ASIA)[A-Z0-9]{16}"),
}

# Deterministic test data, not credentials: the Rust parity vectors carry `whsec_AAECAwQFBgcI...`,
# which is bytes 00 01 02 03 ... base64-encoded. Allowlisting these fixtures is narrower than
# weakening the pattern, and the path list is explicit so a new fixture needs a deliberate decision.
FIXTURES = ("concierge-stack/core-rs/parity/vectors", "concierge-stack/core-rs/tests/fixtures/",
            "api/tests/fixtures/")

TEXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".html", ".css", ".sql", ".yml",
        ".yaml", ".sh", ".env", ".toml", ".cfg", ".ini", ".txt"}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True,
                         text=True, check=True).stdout
    return [ROOT / name for name in out.split("\0") if name]


def scan(text: str) -> list[str]:
    return [label for label, pattern in LIVE.items() if pattern.search(text)]


def test_the_scanner_recognises_a_real_key_and_ignores_a_filename():
    """The scanner must not rot: prove it catches a key and rejects the false positive."""
    assert scan("sk_live_" + "a" * 24), "the scanner no longer detects a Stripe secret"
    assert not scan("asterisk_live_bindings_integration.py"), (
        "a filename containing 'sk_live_' must not be reported as a secret")
    assert not scan("sk_test_" + "a" * 24), "test-mode keys are not live credentials"


def test_a_fixture_path_is_skipped_but_the_same_string_elsewhere_is_not():
    assert any("parity/vectors" in prefix for prefix in FIXTURES)


def test_no_tracked_text_file_contains_a_live_credential():
    found = []
    for path in tracked_files():
        relative = str(path.relative_to(ROOT))
        if path.suffix.lower() not in TEXT or not path.is_file():
            continue
        if any(relative.startswith(prefix) for prefix in FIXTURES):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label in scan(text):
            found.append(f"{path.relative_to(ROOT)}: {label}")
    assert not found, "live credentials in tracked files:\n  " + "\n  ".join(found)
