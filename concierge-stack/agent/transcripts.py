"""Local call transcripts.

Writes what was said on each call to data/transcripts/<date>-<time>-<id>.jsonl on this machine, one
line per turn, appended as it happens. It is written turn by turn on purpose: the console mode can
exit hard, so nothing may wait for a shutdown step.

What it stores: the time, who spoke ("user" is the caller, "assistant" is the agent) and the words.
The file name has no phone number. The folder is owner-only. Transcripts are sensitive: they can hold
names, numbers and what a caller said. Keep them out of git (data/ is ignored), include them in the
encrypted offsite backup when that exists, and keep them only as long as needed.

Settings:
  TRANSCRIPTS=off                disable saving
  TRANSCRIPT_RETENTION_DAYS=30   delete transcripts older than this at startup (0 = keep forever).
                                 30 days, chosen by Jo on 2026-11-07.

This is text only. Audio is NOT recorded here. LiveKit's built-in `record` option uploads audio and
transcripts to LiveKit Cloud, so it is deliberately not used. Audio would be recorded with LiveKit
egress on the VPS, to storage you control.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("trendi-transcripts")


def _dir() -> Path:
    base = os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))
    return Path(base) / "transcripts"


def enabled() -> bool:
    return os.environ.get("TRANSCRIPTS", "on").strip().lower() not in ("off", "0", "false", "no")


def purge_older_than(days: int | None = None) -> int:
    """Delete transcript files older than `days`. Returns how many were removed."""
    if days is None:
        try:
            days = int(os.environ.get("TRANSCRIPT_RETENTION_DAYS", "30"))
        except ValueError:
            days = 30
    folder = _dir()
    if days <= 0 or not folder.is_dir():
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    for path in folder.glob("*.jsonl"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            logger.warning("could not purge a transcript", exc_info=False)
    return removed


class TranscriptWriter:
    """Appends each turn of one call to its own file."""

    def __init__(self, room_name: str) -> None:
        now = datetime.now(timezone.utc)
        short = hashlib.sha256((room_name or "").encode("utf-8")).hexdigest()[:8]
        self.name = f"{now:%Y%m%d-%H%M%S}-{short}.jsonl"
        self.active = enabled()
        self.path = _dir() / self.name
        if self.active:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                os.chmod(self.path.parent, 0o700)
            except OSError:
                logger.warning("transcripts disabled: cannot create folder", exc_info=False)
                self.active = False
        self._write({"event": "call_started"})

    def _write(self, record: dict) -> None:
        if not self.active:
            return
        record = {"at": datetime.now(timezone.utc).isoformat(), **record}
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("transcript write failed", exc_info=False)

    def add(self, role: str, text: str) -> None:
        text = (text or "").strip()
        if text:
            self._write({"role": role, "text": text})

    def on_item(self, ev) -> None:
        """Listener for the session's conversation_item_added event."""
        item = ev.item
        self.add(getattr(item, "role", ""), getattr(item, "text_content", "") or "")
