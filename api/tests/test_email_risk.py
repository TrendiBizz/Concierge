from app import email_risk


def test_unverified_sender_is_flagged_medium():
    result = email_risk.assess(None, "a@example.com", None, "hi", "hello")
    assert result["risk"] == "medium"
    assert "unverified_sender" in result["flags"]


def test_dmarc_fail_is_high_risk():
    result = email_risk.assess({"dmarc": "fail", "spf": "fail"}, "a@example.com", None, "hi", "hello")
    assert result["risk"] == "high"
    assert "dmarc_fail" in result["flags"]


def test_reply_to_mismatch_is_flagged():
    result = email_risk.assess({"dmarc": "pass"}, "a@example.com", "b@other.test", "hi", "hello")
    assert "reply_to_mismatch" in result["flags"]
    assert result["risk"] == "medium"


def test_many_links_raises_risk():
    body = " ".join("https://example.com/%d" % i for i in range(8))
    result = email_risk.assess({"dmarc": "pass"}, "a@example.com", None, "hi", body)
    assert "many_links" in result["flags"]
    assert result["link_count"] == 8


def test_local_link_is_high_risk():
    result = email_risk.assess({"dmarc": "pass"}, "a@example.com", None, "hi",
                               "click http://192.168.1.1/admin")
    assert result["risk"] == "high"
    assert "local_link" in result["flags"]


def test_attachments_are_not_stored():
    result = email_risk.assess({"dmarc": "pass"}, "a@example.com", None, "hi", "hello",
                               has_attachments=True)
    assert "attachments_not_stored" in result["flags"]


def test_oversized_is_high_risk():
    result = email_risk.assess({"dmarc": "pass"}, "a@example.com", None, "hi", "hello",
                               size=250000)
    assert result["risk"] == "high"
    assert "oversized" in result["flags"]


def test_verified_message_is_low_risk():
    result = email_risk.assess(
        {"dmarc": "pass", "spf": "pass", "dkim": "pass", "verified_by": "email-auth"},
        "a@example.com", "a@example.com", "hi", "hello")
    assert result["risk"] == "low"


def test_unverified_pass_hint_is_only_medium():
    result = email_risk.assess({"dmarc": "pass", "spf": "pass", "dkim": "pass"},
                               "a@example.com", None, "hi", "hello")
    assert result["risk"] == "medium"
    assert "unverified_sender" in result["flags"]


def test_verified_pass_beats_failing_spf_hint():
    result = email_risk.assess(
        {"dmarc": "pass", "spf": "fail", "dkim": "pass", "verified_by": "email-auth"},
        "a@example.com", None, "hi", "hello")
    assert result["risk"] == "low"


def test_verified_aligned_dkim_without_dmarc_record_is_low():
    # The reported bug: a genuine reply whose domain publishes no DMARC record
    # (dmarc=none) was flagged unverified_sender/medium even though its DKIM
    # signature passed and aligned with the From domain.
    result = email_risk.assess(
        {"dkim": "pass", "dmarc": "none", "aligned": "yes", "verified_by": "email-auth"},
        "conrad@pukeko.example", None, "Re: kitchen plans", "thanks")
    assert result["risk"] == "low"
    assert "unverified_sender" not in result["flags"]


def test_verified_unaligned_dkim_is_medium_with_its_own_flag():
    result = email_risk.assess(
        {"dkim": "pass", "dmarc": "none", "aligned": "no", "verified_by": "email-auth"},
        "conrad@pukeko.example", None, "hi", "hello")
    assert result["risk"] == "medium"
    assert "dkim_unaligned" in result["flags"]
    assert "unverified_sender" not in result["flags"]


def test_sidecar_failure_is_reported_as_verification_unavailable():
    result = email_risk.assess(
        {"dkim": "pass", "dmarc": "pass", "verification_failed": "yes"},
        "a@example.com", None, "hi", "hello")
    assert result["risk"] == "medium"
    assert "verification_unavailable" in result["flags"]


def test_normal_business_email_size_is_not_oversized():
    # 85 KB is an ordinary HTML email with a signature; it must not be flagged.
    body = "x" * 5000
    result = email_risk.assess(
        {"dmarc": "pass", "spf": "pass", "dkim": "pass", "verified_by": "email-auth",
         "aligned": "yes"},
        "a@example.com", "a@example.com", "hi", body, size=85000)
    assert "oversized" not in result["flags"]
    assert result["risk"] == "low"


def test_dkim_pass_dmarc_none_is_low_when_aligned():
    # The case the DKIM fix was built for: a real small-business sender with no
    # DMARC record. dkim=pass + aligned must not be labelled unverified.
    result = email_risk.assess(
        {"dmarc": "none", "spf": "pass", "dkim": "pass", "verified_by": "email-auth",
         "aligned": "yes"},
        "owner@smallbiz.co.nz", "owner@smallbiz.co.nz", "Quote", "Kia ora, can you quote?",
        size=41234)
    assert result["risk"] == "low"
    assert result["flags"] == []


def test_unaligned_dkim_pass_is_medium_and_not_reported_as_dmarc_fail():
    """A forwarded/list message: a genuine signature from another domain.

    The sidecar emits dmarc="unaligned" for this; before 2026-11-12 it emitted
    "fail", which forced high risk with a factually wrong dmarc_fail flag.
    """
    result = email_risk.assess(
        {"verified_by": "email-auth", "aligned": "no", "dkim": "pass",
         "dmarc": "unaligned", "spf": "pass"},
        "a@example.com", None, "Fwd: hello", "hello")
    assert result["risk"] == "medium"
    assert "dkim_unaligned" in result["flags"]
    assert "dmarc_fail" not in result["flags"]
    assert "auth_fail" not in result["flags"]


def test_aligned_pass_still_beats_an_unaligned_label():
    result = email_risk.assess(
        {"verified_by": "email-auth", "aligned": "yes", "dkim": "pass",
         "dmarc": "pass", "spf": "pass"},
        "a@example.com", None, "hi", "hello")
    assert result["risk"] == "low"
