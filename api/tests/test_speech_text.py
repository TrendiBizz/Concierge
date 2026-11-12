"""Filler words and stutters are removed from outgoing messages; real content is never touched."""
from app.speech_text import clean_speech


def test_the_message_from_the_real_test_call():
    raw = ("Yes, I, I would like an email or a text back, um, to this number, "
           "0 2 7 double 8 1 7 3 6 8, and I want a quotation. Thank you. Bye.")
    assert clean_speech(raw) == ("Yes, I would like an email or a text back to this number, "
                                 "0 2 7 double 8 1 7 3 6 8, and I want a quotation. Thank you. Bye.")


def test_a_sentence_that_opens_with_a_filler_is_capitalised():
    assert clean_speech("Uh, email.") == "Email."
    assert clean_speech("Hmm, let me think, er, tomorrow") == "Let me think tomorrow"


def test_a_filler_at_the_end_keeps_the_full_stop():
    assert clean_speech("I want a quote, um.") == "I want a quote."
    assert clean_speech("Yes. Um. I want it.") == "Yes. I want it."


def test_only_fillers_leave_nothing():
    assert clean_speech("um") == ""
    assert clean_speech("Uh, um, er.") == ""
    assert clean_speech(None) == ""
    assert clean_speech("   ") == ""


def test_stutters_on_short_words_collapse():
    assert clean_speech("I, I, I would like it") == "I would like it"
    assert clean_speech("We want the the roof fixed") == "We want the roof fixed"


def test_real_repeats_and_ordinary_words_survive():
    assert clean_speech("He had had enough") == "He had had enough"
    assert clean_speech("It was that that broke") == "It was that that broke"
    for word in ("umbrella", "errand", "human", "summer", "uh-huh", "Hampton"):
        assert clean_speech(f"The {word} is here") == f"The {word} is here"


def test_numbers_measurements_and_addresses_are_never_touched():
    assert clean_speech("Cut it to 2400 mm please") == "Cut it to 2400 mm please"
    assert clean_speech("K I W I 1 8 at g mail dot com.") == "K I W I 1 8 at g mail dot com."
    assert clean_speech("Call 0 2 7 double 8 1 7 3 6 8") == "Call 0 2 7 double 8 1 7 3 6 8"
