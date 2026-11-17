"""Tests for the backlink pipeline. No network."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backlink_engine as be


class FakeResponse:
    status = 200

    def __init__(self, body=b"<a href='https://trendibizz.com/ai-receptionist'>x</a>"):
        self._body = body

    def read(self, _n=None):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class BacklinkEngineTests(unittest.TestCase):
    def test_queue_is_tier_then_priority(self):
        items = be.queue(5)
        keys = [(int(r["tier"]), int(r["priority"])) for r in items]
        self.assertEqual(keys, sorted(keys))
        self.assertLessEqual(len(items), 5)

    def test_report_has_the_pipeline_numbers(self):
        text = be.report()
        self.assertIn("Prospects: **24**", text)
        self.assertIn("This week's shortlist", text)

    def test_verify_live_when_target_is_present(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            status, note = be.verify_link({
                "source_url": "https://example.com/post",
                "target_url": "https://trendibizz.com/ai-receptionist",
            })
        self.assertEqual(status, "live")
        self.assertIn("found target", note)

    def test_verify_lost_when_target_is_missing(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"<p>nothing</p>")):
            status, note = be.verify_link({
                "source_url": "https://example.com/post",
                "target_url": "https://trendibizz.com/ai-receptionist",
            })
        self.assertEqual(status, "lost")
        self.assertIn("not found", note)


if __name__ == "__main__":
    unittest.main()
