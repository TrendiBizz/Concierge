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
