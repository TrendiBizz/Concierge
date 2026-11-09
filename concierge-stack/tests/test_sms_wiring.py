"""Offline tests for the SMS provider layer and its wiring into notify.py.

No texts are sent and Messages.app is never touched: sends are replaced by fakes and the
Messages database is a throwaway SQLite file.

Run:  concierge-stack/.venv/bin/python -m unittest discover -s concierge-stack/tests -v
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

_TMP = tempfile.TemporaryDirectory()  # used only through patched DATA_DIR inside tests
for var in ("SMTP_HOST", "EMAIL_FROM", "TELNYX_API_KEY", "SMS_FROM", "SMS_PROVIDER"):
    os.environ.pop(var, None)

import notify  # noqa: E402
import sms_providers  # noqa: E402

NUMBER = "+6421000000"  # fake number


def _fake_messages_db(rows):
    """rows: list of (is_sent, error, service) for outgoing messages to NUMBER."""
    path = Path(tempfile.mkdtemp()) / "chat.db"
    db = sqlite3.connect(path)
    db.executescript(
        """
        create table message(ROWID integer primary key, is_from_me int, is_sent int, error int, service text);
        create table chat(ROWID integer primary key, chat_identifier text);
        create table chat_message_join(chat_id int, message_id int);
        """
    )
    db.execute("insert into chat values (1, ?)", (NUMBER,))
    for i, (sent, err, svc) in enumerate(rows, start=1):
        db.execute("insert into message values (?,1,?,?,?)", (i, sent, err, svc))
        db.execute("insert into chat_message_join values (1, ?)", (i,))
    db.commit()
    db.close()
    return path


class VerifyTests(unittest.TestCase):
    def verdict(self, rows, baseline=0):
        with mock.patch.object(sms_providers, "CHAT_DB", _fake_messages_db(rows)):
            return sms_providers.MacMessagesProvider(verify_seconds=3)._verify(baseline, NUMBER)

    def test_error_row_is_failed(self):
        self.assertEqual(self.verdict([(0, 22, "SMS")]), "failed")

    def test_clean_sms_row_is_sent(self):
        self.assertEqual(self.verdict([(1, 0, "SMS")]), "sent")

    def test_imessage_is_not_counted_as_sms(self):
        self.assertEqual(self.verdict([(1, 0, "iMessage")]), "failed")

    def test_no_new_row_is_unverified(self):
        self.assertEqual(self.verdict([]), "unverified")

    def test_old_rows_before_baseline_are_ignored(self):
        self.assertEqual(self.verdict([(1, 0, "SMS")], baseline=1), "unverified")

    def test_unreadable_database_is_unverified_never_sent(self):
        provider = sms_providers.MacMessagesProvider(verify_seconds=1)
        self.assertEqual(provider._verify(None, NUMBER), "unverified")


class WiringTests(unittest.TestCase):
    def send(self, fake_status):
        with mock.patch.dict(
            os.environ, {"SMS_PROVIDER": "mac", "DATA_DIR": _TMP.name}
        ), mock.patch.object(
            sms_providers.MacMessagesProvider, "_send_sync", return_value=fake_status
        ) as fake:
            result = asyncio.run(notify.send_sms(NUMBER, "Hi"))
        return result, fake

    def last_outbox(self):
        lines = (Path(_TMP.name) / "outbox.jsonl").read_text().strip().splitlines()
        return json.loads(lines[-1])

    def test_statuses_pass_through_unchanged(self):
        for status in ("sent", "failed", "unverified"):
            result, fake = self.send(status)
            self.assertEqual(result, status)
            fake.assert_called_once()
            self.assertEqual(self.last_outbox()["status"], status)

    def test_no_provider_still_queues(self):
        with mock.patch.dict(os.environ, {"DATA_DIR": _TMP.name}):
            self.assertEqual(asyncio.run(notify.send_sms(NUMBER, "Hi")), "queued")

    def test_bad_number_fails_before_any_provider(self):
        with mock.patch.dict(
            os.environ, {"SMS_PROVIDER": "mac", "DATA_DIR": _TMP.name}
        ), mock.patch.object(
            sms_providers.MacMessagesProvider, "_send_sync"
        ) as fake:
            self.assertEqual(asyncio.run(notify.send_sms("0210000", "Hi")), "failed")
            fake.assert_not_called()

    def test_unknown_provider_name_is_rejected(self):
        with self.assertRaises(ValueError):
            sms_providers.get_provider("carrier-pigeon")


if __name__ == "__main__":
    unittest.main()
