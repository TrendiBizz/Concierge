"""The telephone opening is two short sentences and never claims more than is true."""
from app import asterisk_bridge as bridge


def _text(**kw):
    base = dict(recording_ok=True, listen_in=False, sms_ok=True)
    base.update(kw)
    return bridge.phone_instructions("Acme Roofing", **base)


def test_opening_is_the_short_two_sentence_greeting():
    text = _text()
    assert "Hello, I'm the AI assistant for Acme Roofing. Our calls are recorded for quality and training purposes.\"" in text
    assert "permission" not in text.lower()


def test_recording_starts_after_the_notice_and_stops_on_objection():
    text = _text()
    assert "call set_call_recording with enabled=true and confirmed=true" in text
    assert "enabled=false at once" in text


def test_it_never_says_recorded_when_recording_is_not_available():
    text = _text(recording_ok=False)
    assert "Our calls are transcribed for quality and training purposes" in text
    assert "Our calls are recorded" not in text
    assert "enabled=true" not in text
    assert "never say or imply that it is" in text


def test_listen_in_is_disclosed_only_when_it_is_possible():
    assert "a team member may listen in" in _text(listen_in=True)
    assert "listen in" not in _text(listen_in=False)
    assert "a team member may listen in" in _text(recording_ok=False, listen_in=True)


def test_questions_are_quick_and_extras_are_not_offered():
    text = _text()
    assert "one short question at a time" in text
    assert "under ten words" in text
    assert "Do not offer a text copy" in text
    assert "callback preference, not a copy of the conversation" in text


def test_earlier_rules_still_apply():
    assert "at most once" in _text()
    assert "Text messages cannot be sent right now" not in _text(sms_ok=True)
    assert "Text messages cannot be sent right now" in _text(sms_ok=False)


def test_business_names_cannot_break_the_quoted_greeting():
    text = bridge.phone_instructions('Bob "The Roof" Ltd', recording_ok=True, listen_in=False, sms_ok=True)
    assert 'for Bob The Roof Ltd.' in text
    assert bridge.phone_instructions("", recording_ok=True, listen_in=False, sms_ok=True).count("for the business.") == 1


def test_the_old_disclosure_helper_still_exists_for_its_own_test():
    assert bridge.greeting_disclosure(False) == ''
