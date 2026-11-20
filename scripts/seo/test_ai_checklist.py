#!/usr/bin/env python3
"""Tests for ai_checklist.py. Run: python3 scripts/seo/test_ai_checklist.py"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_checklist as ac  # noqa: E402

TODAY = date(2026, 11, 20)

GOOD = """<html><head><title>AI SEO</title><meta name="description" content="d">
<link rel="canonical" href="https://x/y">
<script type="application/ld+json">{"@type":"FAQPage","dateModified":"2026-11-10",
"datePublished":"2026-10-01","author":{"@type":"Organization","name":"T"}}</script></head>
<body><main><h1>AI SEO</h1><p>AI SEO makes your pages easy for answer engines to quote accurately.</p>
<h2>What is AI SEO?</h2><p>Short answer with 3 numbers 10 20 30.</p>
<h2>How long does it take?</h2><p>About 6 weeks from setup.</p>
<h2>What does it cost?</h2><p>Plans start at $99 per month.</p>
<h2>What is not included?</h2><p>We can't promise a ranking.</p>
<h2>Compare options</h2><p>Retainer vs project.</p>
<ul><li>a</li></ul><table><tr><td>1</td></tr></table>
<img src="a.png" alt="x"><a href="https://www.linkedin.com/company/x">in</a>
<iframe src="https://www.youtube.com/embed/abc"></iframe></main></body></html>"""

BAD = "<html><head></head><body><h1>A</h1><h1>B</h1><p>" + ("word " * 150) + "</p><img src='a.png'></body></html>"


class AuditTests(unittest.TestCase):
    def test_good_page_scores_high_and_has_no_failures_on_core_items(self):
        r = ac.audit_html("good.html", GOOD, TODAY)
        self.assertGreaterEqual(r.score, 90, r.failed)
        self.assertEqual(r.checks["Updated within 30 days"][1], True)

    def test_bad_page_fails_the_basics(self):
        r = ac.audit_html("bad.html", BAD, TODAY)
        self.assertLess(r.score, 30)
        for name in ("Single H1", "Title and meta description", "Images have an alt attribute (empty is fine for decorative)",
                     "Structured data (JSON-LD) present and valid", "Updated within 30 days"):
            self.assertIn(name, r.failed)

    def test_freshness_boundary(self):
        def page(d: str) -> str:
            return GOOD.replace("2026-11-10", d)
        self.assertTrue(ac.audit_html("p", page("2026-10-21"), TODAY).checks["Updated within 30 days"][1])   # 30 days
        self.assertFalse(ac.audit_html("p", page("2026-10-20"), TODAY).checks["Updated within 30 days"][1])  # 31 days
        self.assertFalse(ac.audit_html("p", page("2026-11-25"), TODAY).checks["Updated within 30 days"][1])  # future

    def test_invalid_jsonld_fails_validity(self):
        r = ac.audit_html("p", GOOD.replace('{"@type":"FAQPage"', '{"@type":"FAQPage",,'), TODAY)
        self.assertIn("Structured data (JSON-LD) present and valid", r.failed)

    def test_noindex_page_is_flagged_not_scored_as_indexable(self):
        html = GOOD.replace('<link rel="canonical"', '<meta name="robots" content="noindex"><link rel="canonical"')
        self.assertTrue(ac.noindex(ac.audit_html("p", html, TODAY)))

    def test_script_text_is_not_counted_as_body_copy(self):
        html = "<html><body><main><h1>A</h1><p>One two three four five six seven eight.</p></main>" \
               "<script>var x = 1 2 3 4 5 6 7 8 9;</script></body></html>"
        r = ac.audit_html("p", html, TODAY)
        self.assertIn("Specific numbers in the body (5 or more)", r.failed)

    def test_decorative_empty_alt_passes_but_missing_alt_fails(self):
        ok = GOOD.replace("</main>", '<img src="i.svg" alt=""></main>')
        self.assertNotIn("Images have an alt attribute (empty is fine for decorative)", ac.audit_html("p", ok, TODAY).failed)
        bad = GOOD.replace("</main>", '<img src="i.svg"></main>')
        self.assertIn("Images have an alt attribute (empty is fine for decorative)", ac.audit_html("p", bad, TODAY).failed)

    def test_eyebrow_label_is_not_the_opening_answer(self):
        html = GOOD.replace("<h1>AI SEO</h1>", "<h1>AI SEO</h1><p>THE FIELD GUIDE</p>")
        self.assertNotIn("Answer-first: first real paragraph is 60 words or less", ac.audit_html("p", html, TODAY).failed)
        long = GOOD.replace("<h1>AI SEO</h1>", "<h1>AI SEO</h1><p>" + "word " * 70 + "</p>")
        self.assertIn("Answer-first: first real paragraph is 60 words or less", ac.audit_html("p", long.replace("AI SEO makes your pages easy for answer engines to quote accurately.", ""), TODAY).failed)

    def test_manual_items_are_never_scored(self):
        r = ac.audit_html("p", GOOD, TODAY)
        for m in ac.MANUAL_ITEMS:
            self.assertNotIn(m, r.checks)


class SiteTests(unittest.TestCase):
    def test_cli_writes_reports_and_skips_404(self):
        with tempfile.TemporaryDirectory() as d:
            site, out = Path(d, "site"), Path(d, "out")
            site.mkdir()
            (site / "a.html").write_text(GOOD)
            (site / "404.html").write_text(BAD)
            self.assertEqual(ac.main(["--site", str(site), "--out", str(out), "--today", "2026-11-20"]), 0)
            self.assertTrue((out / "2026-11-20.csv").exists())
            self.assertIn("a.html", (out / "2026-11-20.md").read_text())
            self.assertNotIn("404.html", (out / "2026-11-20.csv").read_text())

    def test_fail_under_exits_one_and_ignores_noindex_pages(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            (site / "bad.html").write_text(BAD)
            self.assertEqual(ac.main(["--site", str(site), "--today", "2026-11-20", "--fail-under", "60"]), 1)
            (site / "bad.html").write_text(BAD.replace("<head>", '<head><meta name="robots" content="noindex">'))
            self.assertEqual(ac.main(["--site", str(site), "--today", "2026-11-20", "--fail-under", "60"]), 0)

    def test_empty_site_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ac.main(["--site", d]), 2)


if __name__ == "__main__":
    unittest.main()
