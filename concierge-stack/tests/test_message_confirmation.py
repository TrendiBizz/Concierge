"""Offline tests for save_message and the reply the caller chooses (no texts, emails or voice).

Calls the real save_message tool with a stand-in agent object and fake senders, and checks:
nothing is sent unless the caller chose a channel, the right sender is used, statuses are passed
back unchanged, the team is told how to follow up, and a summary that breaks a wording rule
never reaches the caller.

Run:  concierge-stack/.venv/bin/python -m unittest discover -s concierge-stack/tests -v
"""
import asyncio
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

_TMP = tempfile.TemporaryDirectory()
os.environ["MESSAGES_FILE"] = str(Path(_TMP.name) / "messages.jsonl")

import agent  # noqa: E402

REASON = "Wants a callback about SEO for a plumbing business"


def call(**kwargs):
    """Run save_message with fake senders. Returns (result, sms_mock, email_mock)."""
    fake_self = types.SimpleNamespace(
        _room=types.SimpleNamespace(name="test-room"),
        _caller_id=lambda: "+6421000000",
        transcript=types.SimpleNamespace(name="20261107-000000-abcd1234.jsonl"),
    )
    sms = mock.AsyncMock(return_value=kwargs.pop("sms_status", "sent"))
    email = mock.AsyncMock(return_value=kwargs.pop("email_status", "sent"))
    with mock.patch.object(agent.notify, "send_sms", sms), mock.patch.object(
        agent.notify, "send_email", email
    ):
        result = asyncio.run(
            agent.Concierge.save_message(
                fake_self, None, caller_name="Alex Rivera", callback_number="021 000 000",
                reason=REASON, **kwargs,
            )
        )
    return result, sms, email


def owner_alert_only(email):
    """The only email sent should be the owner alert."""
    return email.await_count == 1 and email.await_args.args[0] == agent.OWNER_EMAIL


class ReplyChoiceTests(unittest.TestCase):
    def test_default_sends_nothing_to_the_caller(self):
        result, sms, email = call()
        sms.assert_not_awaited()
        self.assertTrue(owner_alert_only(email))
        self.assertNotIn("reply status", result)

    def test_no_reply_chosen_sends_nothing(self):
        result, sms, email = call(reply_channel="none", followup_method="phone call")
        sms.assert_not_awaited()
        self.assertTrue(owner_alert_only(email))

    def test_unknown_channel_is_treated_as_none(self):
        _, sms, email = call(reply_channel="carrier pigeon")
        sms.assert_not_awaited()
        self.assertTrue(owner_alert_only(email))

    def test_text_short_ack(self):
        result, sms, email = call(reply_channel="text", ack_style="short", followup_method="email")
        sms.assert_awaited_once()
        self.assertEqual(sms.await_args.args[0], "+6421000000")
        body = sms.await_args.args[1]
        self.assertIn("we have your message", body)
        self.assertIn("by email", body)
        self.assertNotIn("SEO", body)
        self.assertTrue(owner_alert_only(email))
        self.assertIn("Text reply status: sent", result)
        self.assertIn("Email reply status: not requested", result)

    def test_text_summary_ack_includes_the_summary(self):
        _, sms, _ = call(
            reply_channel="text", ack_style="summary",
            summary="You asked about SEO and AI visibility for your plumbing business",
            followup_method="phone call",
        )
        body = sms.await_args.args[1]
        self.assertIn("SEO and AI visibility for your plumbing business.", body)
        self.assertIn("by phone call", body)

    def test_summary_with_a_price_or_free_is_dropped(self):
        for bad in ("It is free to start", "SEO is USD 1,500 a month", "We guarantee results"):
            _, sms, _ = call(reply_channel="text", ack_style="summary", summary=bad)
            body = sms.await_args.args[1]
            self.assertNotIn("1,500", body)
            self.assertNotIn("free", body.lower())
            self.assertNotIn("guarantee", body.lower())
            self.assertIn("we have your message.", body)

    def test_email_reply_needs_a_valid_address(self):
        result, sms, email = call(reply_channel="email", email="alex@example.co.nz")
        sms.assert_not_awaited()
        self.assertEqual(email.await_count, 2)  # owner alert + the caller's reply
        self.assertEqual(email.await_args.args[0], "alex@example.co.nz")
        self.assertIn("Email reply status: sent", result)
        result, _, email = call(reply_channel="email", email="not an email")
        self.assertTrue(owner_alert_only(email))
        self.assertIn("Email reply status: failed", result)

    def test_statuses_pass_through_unchanged(self):
        for status in ("queued", "unverified", "failed"):
            result, _, _ = call(reply_channel="text", sms_status=status)
            self.assertIn(f"Text reply status: {status}", result)


class RecordKeepingTests(unittest.TestCase):
    def test_owner_alert_says_how_to_follow_up(self):
        _, _, email = call(
            reply_channel="text", followup_method="phone call", email="alex@example.co.nz"
        )
        body = email.await_args_list[0].args[2]
        self.assertEqual(email.await_args_list[0].args[0], agent.OWNER_EMAIL)
        self.assertIn("Follow up by: phone call", body)
        self.assertIn("alex@example.co.nz", body)
        self.assertIn("Caller asked for a reply by: text", body)

    def test_saved_record_keeps_choices_and_links_the_transcript(self):
        call(reply_channel="email", email="a@b.co", ack_style="summary", followup_method="email")
        last = json.loads(Path(agent.MESSAGES_FILE).read_text().strip().splitlines()[-1])
        self.assertEqual(last["reply_channel"], "email")
        self.assertEqual(last["ack_style"], "summary")
        self.assertEqual(last["followup_method"], "email")
        self.assertEqual(last["transcript"], "20261107-000000-abcd1234.jsonl")


class PromptTests(unittest.TestCase):
    def test_prompt_asks_the_three_questions_and_treats_unverified_as_not_sent(self):
        text = agent.build_instructions()
        for needle in ("reply_channel", "ack_style", "followup_method", '"unverified"'):
            self.assertIn(needle, text)

    def test_concierge_price_matches_the_website(self):
        text = agent.build_instructions()
        self.assertIn("USD 200 a month with", text)
        self.assertIn("USD 2,040", text)
        self.assertIn("15% off", text)
        self.assertIn("will\n   confirm those", text.replace("Trendi team will", "Trendi team will"))
        self.assertNotIn("Give no price", text)

    def test_follow_up_is_asked_first_and_none_ends_the_reply_questions(self):
        rules = agent.SAVE_RULES
        self.assertLess(rules.index("followup_method"), rules.index("reply_channel"))
        self.assertLess(rules.index("reply_channel"), rules.index("ack_style"))
        self.assertIn("If they say none, go straight to saving", rules)
        self.assertNotIn("Ask this even if they want no reply", rules)


if __name__ == "__main__":
    unittest.main()
