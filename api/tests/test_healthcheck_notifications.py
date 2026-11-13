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
