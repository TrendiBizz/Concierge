"""The readiness checker must agree with the API about how a gateway webhook is signed.

If these two ever drift, every real text from the phone would be answered with 403 and the only
symptom would be silence — the failure mode this whole transport exists to avoid.
"""
import hashlib
import hmac
import importlib.util
import pathlib

from app import sms as sms_module

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "vps" / "smsgate_check.py"
_spec = importlib.util.spec_from_file_location("concierge_smsgate_check", SCRIPT)
smsgate_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smsgate_check)


def test_the_checker_signs_exactly_what_the_api_verifies():
    key, body, stamp = "signing-key-from-the-app", b'{"event":"sms:received"}', "1794383230"
    produced = smsgate_check.signature(key, body, stamp)
    assert sms_module.validate_smsgate_signature(key, body, stamp, produced, now=int(stamp))


def test_a_wrong_signature_is_still_wrong():
    key, body, stamp = "signing-key", b'{"event":"sms:received"}', "1794383230"
    produced = smsgate_check.signature(key, body, stamp)
    assert not sms_module.validate_smsgate_signature("other-key", body, stamp, produced, now=int(stamp))


def test_load_env_ignores_comments_and_blank_values(tmp_path):
    env_file = tmp_path / "api.env"
    env_file.write_text("# comment\nSMS_PROVIDER=smsgate\n\nSMSGATE_BASE_URL=\nA=1\n")
    env = smsgate_check.load_env(str(env_file))
    assert env == {"SMS_PROVIDER": "smsgate", "SMSGATE_BASE_URL": "", "A": "1"}


def test_a_missing_env_file_is_not_a_crash():
    assert smsgate_check.load_env("/nonexistent/api.env") == {}
