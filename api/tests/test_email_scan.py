from app import email_scan


def test_classify_clean():
    assert email_scan.classify({"virus": None, "spam_score": 0.5}) == ("low", [])


def test_classify_virus_is_high():
    risk, flags = email_scan.classify({"virus": "stream: Eicar-Test-Signature FOUND"})
    assert risk == "high" and "virus" in flags


def test_classify_spam_thresholds():
    risk, flags = email_scan.classify({"spam_score": 7.5})
    assert risk == "high" and "spam_high" in flags
    risk, flags = email_scan.classify({"spam_score": 3.5})
    assert risk == "medium" and "spam_medium" in flags


def test_classify_empty():
    assert email_scan.classify(None) == ("low", [])
