"""Tests for the GEO daily fingerprint. No network.

Guards the 2026-11-20 defect: Cloudflare stamps a fresh CSP nonce on its injected
Insights beacon on every request, so every page fingerprinted as "changed" each
morning and the whole site was re-pinged to IndexNow daily.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "geo_daily", Path(__file__).resolve().parent / "geo-daily.py")
geo_daily = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(geo_daily)


BODY = """<html><head>
<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js/vabc"
 integrity="sha512-x" nonce="{nonce}"
 data-cf-beacon='{{"version":"2024.11.0","rayId":"{ray}"}}'></script>
<script nonce="{nonce}">window.dataLayer=window.dataLayer||[];</script>
</head><body><h1>AI receptionist</h1>
<script type="application/ld+json">{{"dateModified":"2026-11-19"}}</script>
</body></html>"""


class FingerprintStabilityTest(unittest.TestCase):
    def test_rotating_cloudflare_nonce_does_not_change_fingerprint(self):
        first = geo_daily.fingerprint(BODY.format(nonce="RbodAT2XZmZUMRFIr2SWvA==", ray="r1"))
        second = geo_daily.fingerprint(BODY.format(nonce="drKEzrFJ4lWMZmKc+4KKtA==", ray="r2"))
        self.assertEqual(first, second,
                         "per-request Cloudflare nonce leaked into the fingerprint")

    def test_real_content_change_is_still_detected(self):
        before = geo_daily.fingerprint(BODY.format(nonce="aaa", ray="r1"))
        after = geo_daily.fingerprint(
            BODY.format(nonce="aaa", ray="r1").replace("AI receptionist", "AI answering"))
        self.assertNotEqual(before, after, "genuine content edits must still be seen")


if __name__ == "__main__":
    unittest.main()
