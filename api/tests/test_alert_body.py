"""What the ALERT email says, and whether a polluted report can hide the reason.

The 2026-11-15 mail read "Failing checks: see payload" and named nothing, because alert.sh read a
`checks` key that no report contains (the report has `failures`/`warnings`), and because
healthcheck.sh merged its stderr into the report file, so the JSON often was not JSON at all.
"""
import importlib.util
import json
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps" / "alert_body.py"
_spec = importlib.util.spec_from_file_location("concierge_alert_body", SCRIPT)
alert_body = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(alert_body)

REPORT = {
    "ok": False,
    "counts": {"ok": 37, "warn": 1, "fail": 1},
    "failures": [{"check": "inbound:chain", "status": "fail",
                  "detail": "trendi-support: consent"}],
    "warnings": [{"check": "sms:inbound", "status": "warn", "detail": "never delivered a text"}],
}


def test_the_subject_names_the_failing_check():
    summary = alert_body.summarise(json.dumps(REPORT))
    assert summary["suffix"] == " (inbound:chain)"
    assert summary["failing"] == ["inbound:chain"]


def test_the_body_names_the_reason_not_the_word_payload():
    body = alert_body.summarise(json.dumps(REPORT))["body"]
    assert "FAIL inbound:chain: trendi-support: consent" in body
    assert "warn sms:inbound: never delivered a text" in body
    assert "Counts: ok=37, warn=1, fail=1" in body
    assert "see payload" not in body


def test_a_report_with_a_stray_stderr_line_still_parses():
    """`healthcheck.sh` used to prepend its own note to the JSON."""
    payload = 'deploy grace: trendi-api-1 restarted within 10 minutes\n' + json.dumps(REPORT)
    summary = alert_body.summarise(payload)
    assert summary["failing"] == ["inbound:chain"]
    assert "trendi-support: consent" in summary["body"]


def test_an_unreadable_report_is_still_sent_and_says_so():
    summary = alert_body.summarise("Traceback (most recent call last): boom")
    assert summary["failing"] == []
    assert "not readable as JSON" in summary["body"]
    assert "Traceback" in summary["body"]
