"""The owner asked why a real customer had no name. Their name was in their own signature."""
from app.contact import normalize_phone
from app.email_signature import parse_signature

CONRAD = """We specialize in the supply and installation of Nu-Wall cladding, as well
as replacing existing cladding.

If you have the original plan drawings available, please send them over so
we can review them for your project.

Best regards,

Conrad Schiess
Pukeko Construction
conrad@pukekoconstruction.co.nz

Sent from Gmail Mobile

On Wed, 11 Nov 2026 at 15:13, <admin@trendibizz.com> wrote:
"""


def test_the_real_email_yields_the_persons_name_and_company():
    found = parse_signature(CONRAD)
    assert found["name"] == "Conrad Schiess"
    assert found["company"] == "Pukeko Construction"
    # He gave no number in this message; inventing one would be worse than a blank.
    assert found["phone"] == ""


def test_a_signature_with_a_number_yields_the_number():
    text = ("Thanks for the quick reply.\n\nNgā mihi\nJo Bloggs\nTrendi Ltd\n"
            "021 555 1234\njo@trendi.co.nz\n")
    found = parse_signature(text)
    assert found["name"] == "Jo Bloggs"
    assert found["company"] == "Trendi Ltd"
    assert found["phone"] == "021 555 1234"


def test_a_body_without_a_signature_yields_nothing_rather_than_a_guess():
    assert parse_signature("Hi, can you call me on 027 881 7368? Thanks") == {
        "name": "", "company": "", "phone": ""}
    assert parse_signature("") == {"name": "", "company": "", "phone": ""}


def test_a_quoted_history_is_not_mistaken_for_the_signature():
    text = ("Best regards,\n\nJane Smith\nSmith Builders\n\n"
            "On Tue, 10 Nov 2026, Sam <sam@example.com> wrote:\n> Best regards,\n> Bob Jones\n")
    found = parse_signature(text)
    assert found["name"] == "Jane Smith"
    assert found["company"] == "Smith Builders"


def test_an_unknown_country_code_does_not_invent_one():
    # This is the bug that turned a New Zealand mobile into +10278817368.
    assert normalize_phone("021 555 1234", "") is None
    assert normalize_phone("021 555 1234", "64") == "+64215551234"
    assert normalize_phone("+64 21 555 1234", "") == "+64215551234"


# ---- what people say, on any channel ------------------------------------------------------

def test_details_are_read_from_what_a_visitor_writes():
    from app.identity import extract_details

    found = extract_details("Hi it's Sarah from Acme Construction, can you call me on 021 555 1234", "64")
    assert found["name"] == "Sarah"
    assert found["company"] == "Acme Construction"
    assert found["phone"] == "+64215551234"

    found = extract_details("My name is Conrad Schiess, my email is conrad@pukekoconstruction.co.nz", "64")
    assert found["name"] == "Conrad Schiess"
    assert found["email"] == "conrad@pukekoconstruction.co.nz"


def test_a_plain_question_yields_no_invented_details():
    from app.identity import extract_details

    found = extract_details("We have a two-storey house with old cladding. Do you do that?", "64")
    assert found == {"name": "", "email": "", "phone": "", "company": ""}
    # "I'm interested" is not a person called Interested.
    assert extract_details("I'm interested in a quote thanks", "64")["name"] == ""


def test_a_text_message_signed_with_a_name_keeps_the_name():
    from app.identity import extract_details

    assert extract_details("Can you come out next week?\nSarah", "64")["name"] == "Sarah"


def test_a_long_email_thread_does_not_donate_someone_elses_number():
    from app.identity import extract_details

    body = "Please call me.\n\nOn Tue, Sam wrote:\n> ring the office on 09 555 0000"
    assert extract_details(body, "64", allow_phone=False)["phone"] == ""


def test_a_business_name_is_kept_when_the_phrase_is_not_used():
    from app.identity import extract_details

    found = extract_details("Can you come out Monday morning? Hutt Plumbing\nMaria", "64")
    assert found["company"] == "Hutt Plumbing", "a bare business name was not captured"
    assert found["name"] == "Maria"
    # Ordinary prose must not become a company.
    assert extract_details("the plumbing is old and leaking", "64")["company"] == ""
