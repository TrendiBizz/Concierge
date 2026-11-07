"""SMS providers behind one small contract, so the sender can change without touching the agent.

Contract (same honesty rule as notify.py):
    async def send(to_e164: str, body: str) -> str
returns exactly one of:
    "sent"        the provider confirmed the message left (not just that a command was accepted)
    "failed"      the provider refused it, it errored, or it could not be reached
    "unverified"  the command ran but the outcome could not be read. Treat as NOT sent.
The agent may only tell a caller a text was sent when the status is exactly "sent".
"sent" never means "delivered to the handset": no provider here confirms that.
"queued" (nothing configured) stays notify.py's job, because it owns the outbox.

Providers
    mac    Messages.app on this Mac, through your iPhone's Text Message Forwarding.
           Sends a real SMS from your own NZ number. Works only while the agent runs
           on a Mac that is on, signed in to Messages, with the iPhone on and online.
           Messages accepting the AppleScript command proves nothing (a send can fail
           afterwards), so the outcome is read from Messages' own database,
           ~/Library/Messages/chat.db. macOS blocks that unless the process running this
           code has Full Disk Access. Without it the result is "unverified", never "sent".
    relay  (planned, not built) the agent on a VPS POSTs to a small authenticated
           service on the Mac, which calls the "mac" provider. This keeps your number
           as the sender after the VPS move. Reach the Mac over Tailscale or WireGuard,
           never an open port. Needs SMS_RELAY_URL and SMS_RELAY_TOKEN. The relay service
           is the process that needs Full Disk Access.
    telnyx (existing in notify.py, untested) a hosted API, if you ever want no Mac in the path.

Choose with SMS_PROVIDER=mac|relay|telnyx. Nothing in the agent calls this module yet.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("trendi-sms")

CHAT_DB = Path(os.environ.get("MESSAGES_DB", str(Path.home() / "Library" / "Messages" / "chat.db")))

# The message text and number are passed as arguments (argv), never spliced into the
# script, so quotes or odd characters in a caller's name cannot change what runs.
_SEND_SCRIPT = """
on run argv
    set theNumber to item 1 of argv
    set theText to item 2 of argv
    tell application "Messages"
        set targetService to 1st service whose service type = SMS
        set targetBuddy to buddy theNumber of targetService
        send theText to targetBuddy
    end tell
end run
"""

_CHECK_SCRIPT = """
tell application "Messages"
    return count of (services whose service type = SMS)
end tell
"""


class SmsProvider(Protocol):
    name: str

    async def send(self, to_e164: str, body: str) -> str: ...


def _run_osascript(script: str, args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["osascript", "-e", script, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _open_db() -> sqlite3.Connection:
    # Read-only. Raises sqlite3.Error if macOS blocks access (no Full Disk Access).
    return sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True, timeout=3)


class MacMessagesProvider:
    """Sends an SMS through Messages.app and confirms the outcome from Messages' database."""

    name = "mac"

    def __init__(self, timeout: int = 20, verify_seconds: int = 20) -> None:
        self.timeout = timeout
        self.verify_seconds = verify_seconds

    def can_verify(self) -> tuple[bool, str]:
        """Can this process read Messages' database? Reads only a row count's worth of data."""
        try:
            with _open_db() as db:
                db.execute("select max(ROWID) from message").fetchone()
        except sqlite3.Error:
            return False, (
                "Cannot read the Messages database, so a send can only ever be reported as "
                "'unverified'. Fix: System Settings > Privacy & Security > Full Disk Access, "
                "switch on the app that runs this (for example Terminal), then reopen it."
            )
        return True, "Can read the Messages database, so send results can be verified."

    def check(self) -> tuple[bool, str]:
        """Is an SMS service visible to Messages? Sends nothing. Returns (ok, plain-English reason)."""
        try:
            proc = _run_osascript(_CHECK_SCRIPT, [], self.timeout)
        except FileNotFoundError:
            return False, "osascript not found: this provider only works on a Mac."
        except subprocess.TimeoutExpired:
            return False, "Messages did not answer in time. Is a permission prompt waiting on screen?"
        if proc.returncode != 0:
            return False, "Messages refused the request. Allow Terminal to control Messages in System Settings > Privacy & Security > Automation."
        count = (proc.stdout or "").strip()
        if count.isdigit() and int(count) > 0:
            return True, "Messages has an SMS service."
        return False, (
            "Messages has no SMS service. On the iPhone: Settings > Messages > Text Message "
            "Forwarding, switch this Mac on. Both devices need the same Apple Account."
        )

    @staticmethod
    def _baseline() -> int | None:
        try:
            with _open_db() as db:
                return int(db.execute("select coalesce(max(ROWID), 0) from message").fetchone()[0])
        except sqlite3.Error:
            return None

    @staticmethod
    def _newest_outgoing(baseline: int, to_e164: str):
        """The newest outgoing message after `baseline` in the chat with this number, or None."""
        try:
            with _open_db() as db:
                return db.execute(
                    """
                    select m.is_sent, m.error, m.service
                    from message m
                    join chat_message_join cmj on cmj.message_id = m.ROWID
                    join chat c on c.ROWID = cmj.chat_id
                    where m.is_from_me = 1 and m.ROWID > ? and c.chat_identifier = ?
                    order by m.ROWID desc limit 1
                    """,
                    (baseline, to_e164),
                ).fetchone()
        except sqlite3.Error:
            return None

    def _verify(self, baseline: int | None, to_e164: str) -> str:
        if baseline is None:
            return "unverified"
        deadline = time.monotonic() + self.verify_seconds
        sent_seen = False
        while time.monotonic() < deadline:
            row = self._newest_outgoing(baseline, to_e164)
            if row is not None:
                is_sent, error, service = row
                if error:
                    return "failed"
                if is_sent:
                    if (service or "").upper() != "SMS":
                        return "failed"  # went by iMessage, not as the SMS this provider promises
                    if sent_seen:
                        return "sent"
                    sent_seen = True  # look once more: a failure can be written just after
            time.sleep(1.5 if sent_seen else 1)
        return "unverified"

    def _send_sync(self, to_e164: str, body: str) -> str:
        if not to_e164.startswith("+") or not body.strip():
            return "failed"
        baseline = self._baseline()
        try:
            proc = _run_osascript(_SEND_SCRIPT, [to_e164, body], self.timeout)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("mac sms send failed (osascript missing or timed out)")
            return "failed"
        if proc.returncode != 0:
            # Log only that it failed. The error text can echo the number, so it is not logged.
            logger.warning("mac sms send failed (Messages returned an error)")
            return "failed"
        return self._verify(baseline, to_e164)

    async def send(self, to_e164: str, body: str) -> str:
        return await asyncio.to_thread(self._send_sync, to_e164, body)


def get_provider(name: str | None = None) -> SmsProvider:
    """Return the provider named by SMS_PROVIDER (or the argument). Unbuilt providers raise."""
    chosen = (name or os.environ.get("SMS_PROVIDER", "mac")).strip().lower()
    if chosen == "mac":
        return MacMessagesProvider()
    if chosen in ("relay", "telnyx"):
        raise NotImplementedError(
            f"SMS provider '{chosen}' is not wired into this module yet. See the module docstring."
        )
    raise ValueError(f"Unknown SMS_PROVIDER '{chosen}'. Use mac, relay or telnyx.")
