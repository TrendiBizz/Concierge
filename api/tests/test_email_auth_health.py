"""The domain's own mail authentication must be watched, because it decides whether mail lands.

On 2026-11-15 trendibizz.com published `DMARC p=quarantine` while no DKIM TXT record existed at
any of eight common selectors. A domain that quarantines unauthenticated mail sends its own
customer invitations to Junk, which no open-tracking scheme can fix. The check is DNS-only and
warns rather than fails, because only the operator can publish the record.
"""
import importlib.util
import pathlib
import re

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps" / "healthcheck.py"
_spec = importlib.util.spec_from_file_location("concierge_healthcheck_mail", SCRIPT)
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)

GOOD_SPF = ["v=spf1 include:_spf.mx.cloudflare.net ~all"]
GOOD_DMARC = ["v=DMARC1; p=quarantine; rua=mailto:rua@dmarc.example"]
GOOD_DKIM = ["v=DKIM1; k=rsa; p=MIIBIjANBg"]


def test_a_fully_authenticated_domain_has_no_problems():
    assert healthcheck.email_auth_problems(GOOD_SPF, GOOD_DMARC, GOOD_DKIM) == []


def test_missing_dkim_is_reported():
    problems = healthcheck.email_auth_problems(GOOD_SPF, GOOD_DMARC, [])
    assert len(problems) == 1
    assert "no DKIM record" in problems[0]


def test_a_quarantine_policy_without_dkim_is_the_exact_live_failure():
    problems = healthcheck.email_auth_problems(GOOD_SPF, ["v=DMARC1; p=quarantine"], [])
    assert any("no DKIM" in p for p in problems)


def test_p_equals_none_is_reported_as_unenforced():
    problems = healthcheck.email_auth_problems(GOOD_SPF, ["v=DMARC1; p=none"], GOOD_DKIM)
    assert any("nothing is enforced" in p for p in problems)


def test_missing_spf_and_dmarc_are_reported():
    problems = healthcheck.email_auth_problems([], [], GOOD_DKIM)
    assert "no SPF record" in problems
    assert "no DMARC record" in problems


def test_a_non_spf_txt_record_is_not_mistaken_for_a_policy():
    problems = healthcheck.email_auth_problems(["google-site-verification=abc"], GOOD_DMARC, GOOD_DKIM)
    assert "SPF record is not a v=spf1 policy" in problems


def test_the_check_is_wired_into_the_report():
    source = SCRIPT.read_text()
    loops = re.findall(r"for step in \(([^)]*)\)", source, re.S)
    assert any("check_email_auth" in loop for loop in loops), "check_email_auth must run"
