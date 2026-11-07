"""Offline tests for the acknowledgement wording and the local call transcripts.

Run:  concierge-stack/.venv/bin/python -m unittest discover -s concierge-stack/tests -v
"""
import json
import os
import stat
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

import acknowledge  # noqa: E402
import transcripts  # noqa: E402


class AcknowledgeTests(unittest.TestCase):
    def test_normalising_what_the_model_passes(self):
        self.assertEqual(acknowledge.normalize_channel("SMS"), "text")
        self.assertEqual(acknowledge.normalize_channel("Email"), "email")
        self.assertEqual(acknowledge.normalize_channel("whatever"), "none")
        self.assertEqual(acknowledge.normalize_style("summary"), "summary")
        self.assertEqual(acknowledge.normalize_style("anything else"), "short")
        self.assertEqual(acknowledge.normalize_followup("call"), "phone call")
        self.assertEqual(acknowledge.normalize_followup("email"), "email")
        self.assertEqual(acknowledge.normalize_followup("carrier pigeon"), "")

    def test_short_ack_and_followup_wording(self):
        self.assertEqual(
            acknowledge.build_ack("text", "short", "", "phone call"),
            "Trendi: we have your message. A member of the Trendi team will follow up by phone call. "
            "Questions: admin@trendibizz.com",
        )
        self.assertIn("will follow up.", acknowledge.build_ack("text", "short", "", ""))

    def test_summary_is_used_only_when_asked_for(self):
        self.assertIn("plumbing", acknowledge.build_ack("email", "summary", "About plumbing SEO", "email"))
        self.assertNotIn("plumbing", acknowledge.build_ack("email", "short", "About plumbing SEO", "email"))

    def test_broken_wording_rules_fall_back_to_short(self):
        short = acknowledge.build_ack("text", "short", "", "email")
        for bad in ("It is free", "USD 1,500", "$100 a month", "100% sure", "We promise a call"):
            self.assertEqual(acknowledge.build_ack("text", "summary", bad, "email"), short, bad)

    def test_no_exclamation_marks(self):
        self.assertNotIn("!", acknowledge.build_ack("email", "summary", "Great news!", ""))

    def test_text_is_trimmed_to_two_segments_but_email_is_not(self):
        long_summary = "You asked about " + "search visibility and AI mentions for your business " * 12
        text = acknowledge.build_ack("text", "summary", long_summary, "email")
        self.assertLessEqual(len(text), acknowledge.TEXT_LIMIT)
        self.assertIn("...", text)
        self.assertTrue(text.endswith("Questions: admin@trendibizz.com"))
        email = acknowledge.build_ack("email", "summary", long_summary, "email")
        self.assertGreater(len(email), acknowledge.TEXT_LIMIT)
        self.assertNotIn("...", email)


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.dict(os.environ, {"DATA_DIR": self._dir.name})
        self._patch.start()
        os.environ.pop("TRANSCRIPTS", None)

    def tearDown(self):
        self._patch.stop()
        self._dir.cleanup()

    def lines(self, writer):
        return [json.loads(line) for line in writer.path.read_text().splitlines()]

    def test_turns_are_appended_and_the_name_hides_the_number(self):
        writer = transcripts.TranscriptWriter("call-_+6421000000_abc")
        item = types.SimpleNamespace(role="user", text_content="Hello there")
        writer.on_item(types.SimpleNamespace(item=item))
        writer.add("assistant", "Which service?")
        writer.add("assistant", "   ")  # blank turns are skipped
        rows = self.lines(writer)
        self.assertEqual([r.get("role") for r in rows], [None, "user", "assistant"])
        self.assertEqual(rows[1]["text"], "Hello there")
        self.assertNotIn("6421000000", writer.name)

    def test_files_are_owner_only(self):
        writer = transcripts.TranscriptWriter("room")
        writer.add("user", "hi")
        self.assertEqual(stat.S_IMODE(writer.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(writer.path.parent.stat().st_mode), 0o700)

    def test_can_be_switched_off(self):
        os.environ["TRANSCRIPTS"] = "off"
        writer = transcripts.TranscriptWriter("room")
        writer.add("user", "hi")
        self.assertFalse(writer.path.exists())

    def test_purge_removes_only_old_files(self):
        old = transcripts.TranscriptWriter("old")
        new = transcripts.TranscriptWriter("new")
        old.add("user", "x")
        new.add("user", "y")
        past = time.time() - 100 * 86400
        os.utime(old.path, (past, past))
        self.assertEqual(transcripts.purge_older_than(90), 1)
        self.assertFalse(old.path.exists())
        self.assertTrue(new.path.exists())

    def test_default_retention_is_30_days(self):
        os.environ.pop("TRANSCRIPT_RETENTION_DAYS", None)
        old = transcripts.TranscriptWriter("old")
        recent = transcripts.TranscriptWriter("recent")
        old.add("user", "x")
        recent.add("user", "y")
        for writer, age in ((old, 40), (recent, 20)):
            stamp = time.time() - age * 86400
            os.utime(writer.path, (stamp, stamp))
        self.assertEqual(transcripts.purge_older_than(), 1)
        self.assertFalse(old.path.exists())
        self.assertTrue(recent.path.exists())

    def test_zero_days_keeps_everything(self):
        writer = transcripts.TranscriptWriter("room")
        writer.add("user", "x")
        past = time.time() - 1000 * 86400
        os.utime(writer.path, (past, past))
        self.assertEqual(transcripts.purge_older_than(0), 0)
        self.assertTrue(writer.path.exists())


if __name__ == "__main__":
    unittest.main()
