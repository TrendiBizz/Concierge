"""site_seo.audit must flag titles over 60 chars and the retired HowTo schema type. No network."""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_seo


def page(title, ld=""):
    return (f'<html><head><title>{title}</title><meta name="description" content="d">'
            f'{ld}</head><body><h1>x</h1></body></html>')


class TitleAndSchema(unittest.TestCase):
    def run_audit(self, html):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "p.html").write_text(html)
            (Path(d) / "indexnow-key.json").write_text((site_seo.SITE_ROOT / "indexnow-key.json").read_text())
            return site_seo.audit(Path(d))

    def test_long_title_flagged(self):
        self.assertTrue(any("limit 60" in x for x in self.run_audit(page("x" * 61))))

    def test_short_title_not_flagged(self):
        self.assertFalse(any("limit 60" in x for x in self.run_audit(page("x" * 60))))

    def test_howto_flagged(self):
        ld = '<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"HowTo","name":"n"}]}</script>'
        self.assertTrue(any("deprecated schema type HowTo" in x for x in self.run_audit(page("ok", ld))))


if __name__ == "__main__":
    unittest.main()
