"""What the healthcheck decides to email, tested without a live stack.

The live check re-emailed the same failing condition whenever its detail grew ("consent" became
"consent,mailbox"), so one broken thing produced a stream of identical-looking alerts. The rule
is now: claim on the status; a detail change updates what the next reminder says, silently.

`plan_notifications` is imported from the VPS script by path, because the script runs on the host
and is not installed as a package.
"""
import importlib.util
import pathlib
from datetime import datetime, timedelta, timezone

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps" / "healthcheck.py"
_spec = importlib.util.spec_from_file_location("concierge_healthcheck", SCRIPT)
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)

NOW = datetime(2026, 11, 13, 14, 0, tzinfo=timezone.utc)


def a_problem(detail="trendi-support: consent", status="fail", check="inbound:chain"):
    return {check: {"check": check, "status": status, "detail": detail}}


def test_a_new_failure_is_emailed_once():
    state = {}
    alerts, reminders, recoveries = healthcheck.plan_notifications(a_problem(), state, NOW)
    assert len(alerts) == 1 and reminders == [] and recoveries == []
    assert state["inbound:chain"]["last_sent"] == NOW.isoformat()


def test_a_wordier_detail_does_not_email_again():
    """The bug: the same broken thing, described in more detail, must not send another email."""
    state = {}
    healthcheck.plan_notifications(a_problem("trendi-support: consent"), state, NOW)
    later = NOW + timedelta(minutes=20)
    alerts, reminders, _ = healthcheck.plan_notifications(
        a_problem("trendi-support: consent,mailbox"), state, later)
    assert alerts == [], "a detail change is not a new problem"
    assert reminders == [], "and it is not yet time for a reminder"
    assert state["inbound:chain"]["detail"] == "trendi-support: consent,mailbox", \
        "but the next reminder must describe the current state"


def test_a_still_broken_condition_reminds_once_the_window_passes():
    state = {}
    healthcheck.plan_notifications(a_problem(), state, NOW)
    alerts, reminders, _ = healthcheck.plan_notifications(
        a_problem(), state, NOW + timedelta(hours=7))
    assert alerts == [] and len(reminders) == 1


def test_going_from_fail_to_warn_is_a_new_alert():
    state = {}
    healthcheck.plan_notifications(a_problem(status="fail"), state, NOW)
    alerts, _, _ = healthcheck.plan_notifications(a_problem(status="warn"), state, NOW)
    assert len(alerts) == 1, "a change of severity is worth being told about"


def test_recovery_is_announced_and_the_state_is_cleared():
    state = {}
    healthcheck.plan_notifications(a_problem(), state, NOW)
    alerts, reminders, recoveries = healthcheck.plan_notifications({}, state, NOW)
    assert alerts == [] and reminders == []
    assert recoveries == [{"check": "inbound:chain", "was": "fail", "since": NOW.isoformat()}]
    assert "inbound:chain" not in state, "a healthy check must not be remembered as broken"


def test_a_quiet_check_never_enters_the_state():
    state = {}
    healthcheck.plan_notifications({}, state, NOW)
    assert state == {}


def test_a_check_that_nobody_here_can_fix_is_never_emailed():
    """`sms:inbound` means the paired phone has never delivered a text. No reminder makes that happen."""
    problems = {"sms:inbound": {"check": "sms:inbound", "status": "warn", "detail": "never delivered"}}
    assert healthcheck.mailable(problems) == {}

    state = {}
    alerts, reminders, recoveries = healthcheck.plan_notifications(healthcheck.mailable(problems), state, NOW)
    assert alerts == [] and reminders == [] and recoveries == []
    assert state == {}, "a status-only check must not touch alert state"

    # A real problem still reaches the operator.
    real = {"inbound:chain": {"check": "inbound:chain", "status": "fail", "detail": "consent"}}
    alerts, _, _ = healthcheck.plan_notifications(healthcheck.mailable(real), {}, NOW)
    assert len(alerts) == 1


def test_a_deploy_restart_is_recognised_as_deploying(monkeypatch):
    """A container restarted moments ago means a deploy is in flight: no mail, no state change."""
    monkeypatch.setattr(healthcheck, "recently_started", lambda name, minutes=10: name == "trendi-api-1")
    assert healthcheck.deploying() == "trendi-api-1"

    monkeypatch.setattr(healthcheck, "recently_started", lambda name, minutes=10: False)
    assert healthcheck.deploying() == ""


def _inbound_stub(tenants):
    """Run check_inbound against a canned readiness payload, with no stack involved."""
    import json
    healthcheck.http = lambda *a, **k: (200, json.dumps({"tenants": tenants}).encode(), 0.0)
    healthcheck.run = lambda *a, **k: (0, "0")
    return healthcheck.check_inbound({"ADMIN_TOKEN": "t"})


def test_an_incomplete_test_tenant_is_reported_and_never_fails_the_check():
    """2026-11-15: the hourly mail said fail=1 for trendi-fictitious, a fictitious business."""
    results = _inbound_stub([
        {"slug": "acme", "ok": True},
        {"slug": "trendi-fictitious", "ok": False, "is_test": True,
         "blocked": [{"check": "consent"}]},
    ])
    chain = next(r for r in results if r["check"] == "inbound:chain")
    assert chain["status"] == "ok", chain
    assert "trendi-fictitious is a test tenant" in chain["detail"]


def test_a_broken_real_tenant_still_fails_the_check():
    results = _inbound_stub([{"slug": "acme", "ok": False, "blocked": [{"check": "mailbox"}]}])
    chain = next(r for r in results if r["check"] == "inbound:chain")
    assert chain["status"] == "fail"
    assert "acme: mailbox" in chain["detail"]


def test_the_sms_warning_alone_never_emails():
    """The paired phone has never received a text. Nothing we can do here changes that, so it is
    reported in every run and must never be the reason a mail is sent — otherwise the operator
    gets one an hour about a capability, not a fault."""
    problems = {"sms:inbound": {"check": "sms:inbound", "status": "warn",
                                "detail": "1 of 1 paired phone(s) have never delivered a text in"}}
    assert healthcheck.mailable(problems) == {}
    alerts, reminders, recoveries = healthcheck.plan_notifications(
        healthcheck.mailable(problems), {}, NOW)
    assert (alerts, reminders, recoveries) == ([], [], [])


def test_a_real_failure_still_emails_alongside_that_warning():
    problems = {
        "sms:inbound": {"check": "sms:inbound", "status": "warn", "detail": "never delivered"},
        "inbound:chain": {"check": "inbound:chain", "status": "fail", "detail": "acme: consent"},
    }
    alerts, _, _ = healthcheck.plan_notifications(healthcheck.mailable(problems), {}, NOW)
    assert [a["check"] for a in alerts] == ["inbound:chain"]
