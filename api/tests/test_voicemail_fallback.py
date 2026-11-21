"""N3: voicemail fallback — dialplan generation and spool ingestion."""
import asyncio
import importlib.util
import os
import time
from pathlib import Path

import pytest

from app import voicemail_fallback as vf

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "asterisk" / "render_routes.py"
_spec = importlib.util.spec_from_file_location("render_routes_n3", _PATH)
rr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rr)

TRUNK = {"server": "sip.example.invalid", "username": "092431347", "password": "correct-horse-battery", "transport": "udp", "port": 5060}
ROW = {"tenant": "pukeko-construction", "number": "+6492431347", "port": 9510}


def _body(ext, name="business-pukeko-construction"):
    lines = ext.splitlines()
    out = []
    for line in lines[lines.index("[" + name + "]") + 1:]:
        if line.startswith("["):
            break
        out.append(line)
    return out


def test_dialplan_unchanged_without_voicemail_dir():
    ext, _ = rr.render([ROW], "bridge", "1.2.3.4", TRUNK)
    assert "Record(" not in ext and "voicemail" not in ext


def test_dialplan_records_voicemail_after_audiosocket_returns():
    ext, _ = rr.render([ROW], "bridge", "1.2.3.4", TRUNK, voicemail_dir="/var/spool/concierge-voicemail")
    body = _body(ext)
    audio = next(i for i, l in enumerate(body) if "AudioSocket(" in l)
    rec = next(i for i, l in enumerate(body) if "Record(/var/spool/concierge-voicemail/pukeko-construction__" in l)
    assert audio < rec and body[-1] == " same => n,Hangup()"
    assert not any("Dial(" in l for l in body)  # no owner number configured


def test_dialplan_rings_owner_before_voicemail_when_configured():
    row = {**ROW, "ring_owner": {"number": "+6421824305", "seconds": 15}}
    body = _body(rr.render([row], "bridge", "1.2.3.4", TRUNK, voicemail_dir="/var/spool/vm")[0])
    audio = next(i for i, l in enumerate(body) if "AudioSocket(" in l)
    dials = [i for i, l in enumerate(body) if "Dial(PJSIP/6421824305" in l]
    rec = next(i for i, l in enumerate(body) if "Record(" in l)
    assert len(dials) == 2 and audio < dials[1] < rec


def test_dialplan_rejects_unsafe_voicemail_dir():
    with pytest.raises(ValueError):
        rr.render([ROW], "bridge", "1.2.3.4", TRUNK, voicemail_dir="/tmp/x;System(rm)")


def test_parse_name():
    assert vf.parse_name("pukeko-construction__abc-123def45__6421555123.wav")["num"] == "6421555123"
    assert vf.parse_name("../evil__x__1.wav") is None
    assert vf.parse_name("a__b__c.mp3") is None


def _make(path, size, age):
    path.write_bytes(b"\0" * size)
    t = time.time() - age
    os.utime(path, (t, t))


def test_sweep_stores_removes_and_ignores(tmp_path, monkeypatch):
    seen = []

    async def fake_tenant(slug):
        return {"id": "t1"} if slug == "pukeko-construction" else None

    async def fake_process(path, tenant, parts):
        seen.append(parts["call"])
        return "stored"
    monkeypatch.setattr(vf.tenants, "get_by_slug", fake_tenant)
    monkeypatch.setattr(vf, "_process", fake_process)
    _make(tmp_path / "pukeko-construction__aaaaaaaa-1__6421555123.wav", 20000, 60)   # stored
    _make(tmp_path / "pukeko-construction__aaaaaaaa-2__6421555123.wav", 20000, 1)    # still being written
    _make(tmp_path / "pukeko-construction__aaaaaaaa-3__.wav", 100, 60)               # silence: deleted
    _make(tmp_path / "nobody__aaaaaaaa-4__6421555123.wav", 20000, 60)                # unknown tenant: left
    _make(tmp_path / "junk.wav", 20000, 60)                                          # bad name: left
    result = asyncio.run(vf.sweep(str(tmp_path)))
    assert seen == ["aaaaaaaa-1"] and result["stored"] == 1
    assert not (tmp_path / "pukeko-construction__aaaaaaaa-1__6421555123.wav").exists()
    assert not (tmp_path / "pukeko-construction__aaaaaaaa-3__.wav").exists()
    assert (tmp_path / "pukeko-construction__aaaaaaaa-2__6421555123.wav").exists()
    assert (tmp_path / "nobody__aaaaaaaa-4__6421555123.wav").exists() and (tmp_path / "junk.wav").exists()


def test_sweep_keeps_file_when_processing_fails(tmp_path, monkeypatch):
    async def fake_tenant(slug):
        return {"id": "t1"}

    async def boom(*a):
        raise RuntimeError("db down")
    monkeypatch.setattr(vf.tenants, "get_by_slug", fake_tenant)
    monkeypatch.setattr(vf, "_process", boom)
    f = tmp_path / "pukeko-construction__aaaaaaaa-1__6421555123.wav"
    _make(f, 20000, 60)
    result = asyncio.run(vf.sweep(str(tmp_path)))
    assert result["errors"] == 1 and f.exists()


def test_sweep_off_without_directory():
    assert asyncio.run(vf.sweep("")) == {"stored": 0, "kept": 0, "duplicate": 0, "skipped": 0, "errors": 0}
