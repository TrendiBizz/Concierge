"""Offline tests for the CRM adapter (calls to the Twenty lead bridge). A tiny local HTTP server stands in for the bridge,
so no network, no Twenty and no real data are involved.

Run:  concierge-stack/.venv/bin/python -m unittest discover -s concierge-stack/tests -v
"""
import asyncio
import inspect
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

_TMP = tempfile.TemporaryDirectory()
os.environ["MESSAGES_FILE"] = str(Path(_TMP.name) / "messages.jsonl")

import agent  # noqa: E402
import crm  # noqa: E402


class FakeBridge:
    """Answers POST /lead with a chosen status and body, and remembers what it was sent."""

    def __init__(self, status=200, body=None):
        self.status, self.body, self.received = status, body or {"ok": True, "duplicate": False}, []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                outer.received.append(json.loads(self.rfile.read(length)))
                data = json.dumps(outer.body).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/lead"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def push(url, **kw):
    env = {"DATA_DIR": _TMP.name, "CRM_BRIDGE_URL": url}
    args = dict(name="Alex Rivera", phone="021 000 000", email="", message="Wants a callback", plan="", source="Voice call")
    args.update(kw)
    with mock.patch.dict(os.environ, env):
        return asyncio.run(crm.push_lead(**args))


class AdapterTests(unittest.TestCase):
    def test_accepted_lead_is_sent_and_shaped_correctly(self):
        bridge = FakeBridge()
        self.addCleanup(bridge.close)
        self.assertEqual(push(bridge.url, email="alex@example.co.nz", plan="SEO"), "sent")
        sent = bridge.received[0]
        self.assertEqual((sent["first_name"], sent["last_name"]), ("Alex", "Rivera"))
        self.assertEqual(sent["phone"], "+6421000000")
        self.assertEqual(sent["email"], "alex@example.co.nz")
        self.assertEqual((sent["message"], sent["plan"], sent["source"]), ("Wants a callback", "SEO", "Voice call"))
        self.assertNotIn("website", sent)  # the bridge's honeypot field must stay absent

    def test_duplicate_counts_as_sent(self):
        bridge = FakeBridge(body={"ok": True, "duplicate": True})
        self.addCleanup(bridge.close)
        self.assertEqual(push(bridge.url), "sent")

    def test_refused_is_failed(self):
        for status in (400, 429, 502, 503):
            bridge = FakeBridge(status=status, body={"ok": False})
            self.addCleanup(bridge.close)
            self.assertEqual(push(bridge.url), "failed", status)

    def test_ok_false_is_failed(self):
        bridge = FakeBridge(body={"ok": False})
        self.addCleanup(bridge.close)
        self.assertEqual(push(bridge.url), "failed")

    def test_unreachable_bridge_is_failed_and_never_raises(self):
        self.assertEqual(push("http://127.0.0.1:1/lead"), "failed")

    def test_not_configured_is_queued(self):
        self.assertEqual(push(""), "queued")

    def test_no_phone_or_email_cannot_be_sent(self):
        bridge = FakeBridge()
        self.addCleanup(bridge.close)
        self.assertEqual(push(bridge.url, phone="", email=""), "failed")
        self.assertEqual(bridge.received, [])

    def test_single_word_name(self):
        bridge = FakeBridge()
        self.addCleanup(bridge.close)
        push(bridge.url, name="Madonna")
        self.assertEqual((bridge.received[0]["first_name"], bridge.received[0].get("last_name", "")), ("Madonna", ""))


class WiringTests(unittest.TestCase):
    def test_saving_a_message_sends_it_to_the_crm(self):
        fake_self = types.SimpleNamespace(
            _room=types.SimpleNamespace(name="test-room"), _caller_id=lambda: "+6421000000", transcript=None
        )
        push_mock = mock.AsyncMock(return_value="sent")
        with mock.patch.dict(os.environ, {"DATA_DIR": _TMP.name}), mock.patch.object(
            agent.notify, "send_email", mock.AsyncMock(return_value="sent")
        ), mock.patch.object(agent.crm, "push_lead", push_mock):
            asyncio.run(
                agent.Concierge.save_message(
                    fake_self, None, caller_name="Alex Rivera", callback_number="021 000 000", reason="Wants SEO help"
                )
            )
        push_mock.assert_awaited_once()
        kwargs = push_mock.await_args.kwargs
        self.assertEqual((kwargs["name"], kwargs["message"]), ("Alex Rivera", "Wants SEO help"))
        self.assertIn("message", kwargs["source"].lower())

    def test_a_booking_is_wired_to_the_crm(self):
        self.assertIn("crm.push_lead", inspect.getsource(agent.Concierge.book_appointment))


if __name__ == "__main__":
    unittest.main()
