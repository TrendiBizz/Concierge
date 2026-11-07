"""Offline tests: no network, no API key, temporary data directory.

Run:  concierge-stack/.venv/bin/python -m unittest discover -s concierge-stack/tests -v
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

_TMP = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _TMP.name
for var in ("SMTP_HOST", "EMAIL_FROM", "TELNYX_API_KEY", "SMS_FROM"):
    os.environ.pop(var, None)

import booking  # noqa: E402
import notify  # noqa: E402

MONDAY_8AM = datetime(2026, 11, 9, 8, 0, tzinfo=booking.TZ)  # NZ summer time (UTC+13)


class BookingTests(unittest.TestCase):
    def test_hours_notice_and_weekend(self):
        slots = booking.available_slots(date(2026, 11, 9), MONDAY_8AM)
        self.assertEqual(slots[0].hour, 10)  # 2 hours notice from 8am
        self.assertEqual((slots[-1].hour, slots[-1].minute), (16, 30))
        self.assertEqual(booking.available_slots(date(2026, 11, 14), MONDAY_8AM), [])  # Saturday

    def test_no_double_booking(self):
        slot = "2026-11-10T11:00:00+13:00"
        appt = booking.book(slot, "Test Caller", "+6421000000", "", "Concierge", now=MONDAY_8AM)
        self.assertEqual(appt.start.hour, 11)
        with self.assertRaises(booking.BookingError):
            booking.book(slot, "Someone Else", "", "", "SEO", now=MONDAY_8AM)
        remaining = booking.available_slots(date(2026, 11, 10), MONDAY_8AM)
        self.assertNotIn(appt.start, remaining)

    def test_outside_hours_rejected(self):
        with self.assertRaises(booking.BookingError):
            booking.book("2026-11-10T20:00:00+13:00", "X", "", "", "SEO", now=MONDAY_8AM)

    def test_ics_is_utc_and_spoken_is_local(self):
        appt = booking.book(
            "2026-11-11T10:00:00+13:00", "Ics Test", "", "", "Penetration testing", now=MONDAY_8AM
        )
        text = booking.ics(appt)
        self.assertIn("DTSTART:20261110T210000Z", text)  # 10:00 NZDT = 21:00 UTC the day before
        self.assertEqual(booking.spoken(appt.start), "Wednesday 11 November at 10:00 am")

    def test_next_available_spans_days(self):
        self.assertEqual(len(booking.next_available(6, MONDAY_8AM)), 6)


class NotifyTests(unittest.TestCase):
    def test_e164(self):
        self.assertEqual(notify.to_e164("022 000 0000"), "+64220000000")
        self.assertEqual(notify.to_e164("+61 400 000 000"), "+61400000000")
        self.assertEqual(notify.to_e164("0064 21 000 000"), "+6421000000")
        self.assertEqual(notify.to_e164("12"), "")
        self.assertEqual(notify.to_e164(""), "")

    def test_email_validation(self):
        self.assertTrue(notify.valid_email("a@b.co"))
        self.assertFalse(notify.valid_email("not an email"))

    def test_unconfigured_providers_queue_honestly(self):
        self.assertEqual(asyncio.run(notify.send_email("a@b.co", "Hi", "Body")), "queued")
        self.assertEqual(asyncio.run(notify.send_sms("+6421000000", "Hi")), "queued")
        lines = (Path(_TMP.name) / "outbox.jsonl").read_text().strip().splitlines()
        self.assertTrue(all(json.loads(line)["status"] == "queued" for line in lines[-2:]))

    def test_bad_destinations_fail(self):
        self.assertEqual(asyncio.run(notify.send_email("nope", "Hi", "Body")), "failed")
        self.assertEqual(asyncio.run(notify.send_sms("0210000", "Hi")), "failed")


if __name__ == "__main__":
    unittest.main()
