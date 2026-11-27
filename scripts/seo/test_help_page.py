"""/help hub: 7 stage videos present, banner on key pages, footer link on every page. No network."""
import re, unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "website"


class HelpPage(unittest.TestCase):
    def test_hub_has_all_stage_videos(self):
        t = (WEB / "help.html").read_text()
        self.assertEqual(t.count("<h1"), 1)
        for n in range(1, 8):
            self.assertIn(f'src="/media/help/stage-{n}.mp4"', t)
            self.assertIn(f'src="/media/help/stage-{n}.vtt"', t)
            self.assertTrue((WEB / f"media/help/stage-{n}.mp4").exists())
            self.assertTrue((WEB / f"media/help/stage-{n}.vtt").exists())
            self.assertIn(f"help-stage-{n}-video", t)

    def test_banner_on_key_pages(self):
        for p in ["guide", "concierge", "concierge-start", "contact", "pricing"]:
            t = (WEB / f"{p}.html").read_text()
            self.assertEqual(t.count("help-banner"), 1, p)
            self.assertIn('href="/help"', t, p)

    def test_footer_links_to_help_everywhere(self):
        for p in WEB.glob("**/*.html"):
            t = p.read_text()
            if 'aria-label="Explore" class="footer-nav"' in t:
                self.assertIn('<a href="/help">Help and onboarding</a>', t, str(p))


if __name__ == "__main__":
    unittest.main()
