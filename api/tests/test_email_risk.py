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
                               size=50000)
    assert result["risk"] == "high"
    assert "oversized" in result["flags"]


def test_clean_authenticated_message_is_low_risk():
    result = email_risk.assess({"dmarc": "pass", "spf": "pass", "dkim": "pass"},
                               "a@example.com", "a@example.com", "hi", "hello")
    assert result["risk"] == "low"
    assert result["flags"] == []
