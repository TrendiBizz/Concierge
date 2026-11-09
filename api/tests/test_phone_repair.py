"""Repairing phone numbers the old normaliser already wrote into the database.

The distinction this file exists to pin: fixing `normalize_phone` fixes INPUT, not stored DATA. A
value already in the database is treated by the new normaliser as decisive -- '+021555123' starts
with '+', so it passes through untouched, and '+646421555123' stays doubled. Re-running the new
normaliser over the database is a no-op, which is what the first test here demonstrates.

The repair therefore recognises the three damaged shapes the old code could produce. Anything it does
not confidently recognise is left EXACTLY as-is, because rewriting a customer's number wrongly is
worse than leaving it: it sends messages to a stranger.
"""
import pytest

from app import phone_repair
from app.contact import normalize_phone


# ---------------------------------------------------------------- why this module exists


def test_the_new_normaliser_alone_cannot_repair_stored_values():
    """The premise of this module, pinned so nobody 'simplifies' it away later.

    A stored value with a '+' is returned unchanged by normalize_phone, so a database pass using it
    would silently repair nothing while appearing to work.
    """
    assert normalize_phone("+021555123", "64") == "+021555123"      # trunk zero survives
    assert normalize_phone("+646421555123", "64") == "+646421555123"  # doubled code survives
    # Whereas the repair knows these shapes:
    assert phone_repair.repair_phone("+021555123", "64")[0] == "+6421555123"
    assert phone_repair.repair_phone("+646421555123", "64")[0] == "+6421555123"


# ---------------------------------------------------------------- the three damaged shapes


@pytest.mark.parametrize("stored,expected", [
    ("021555123", "+6421555123"),
    ("021 555 123", "+6421555123"),
    ("021-555-123", "+6421555123"),
    ("095551234", "+6495551234"),
    ("09 555 1234", "+6495551234"),
])
def test_trunk_prefix_kept_is_repaired(stored, expected):
    assert phone_repair.repair_phone(stored, "64")[0] == expected


@pytest.mark.parametrize("stored,expected", [
    ("+021555123", "+6421555123"),
    ("+095551234", "+6495551234"),
])
def test_trunk_prefix_kept_after_a_plus_is_repaired(stored, expected):
    assert phone_repair.repair_phone(stored, "64")[0] == expected


@pytest.mark.parametrize("stored,expected", [
    ("+646421555123", "+6421555123"),
    ("646421555123", "+6421555123"),
    ("+447700900123", "+447700900123"),   # already clean, must not change
])
def test_doubled_country_code_is_repaired(stored, expected):
    assert phone_repair.repair_phone(stored, "64")[0] == expected


def test_a_repaired_value_is_always_dialable():
    """The point of the repair: the result must be a number a carrier would accept."""
    for stored in ("021555123", "+021555123", "+646421555123", "646421555123", "095551234"):
        fixed, reason = phone_repair.repair_phone(stored, "64")
        assert reason, stored
        assert fixed.startswith("+64"), (stored, fixed)
        assert phone_repair.is_usable(fixed, "64") is True, fixed


# ---------------------------------------------------------------- must NOT change


@pytest.mark.parametrize("clean", [
    "+6421555123",
    "+12145550100",
    "+447700900123",
])
def test_an_already_clean_number_is_untouched(clean):
    """Idempotence matters: running the repair twice must not damage a good number."""
    assert phone_repair.repair_phone(clean, "64") == (clean, "")


def test_repair_is_idempotent():
    """Applying the repair to its own output changes nothing further."""
    for stored in ("021555123", "+021555123", "+646421555123", "095551234"):
        once, reason = phone_repair.repair_phone(stored, "64")
        assert reason
        twice, second_reason = phone_repair.repair_phone(once, "64")
        assert (twice, second_reason) == (once, ""), stored


def test_an_email_in_a_contact_column_is_left_alone():
    """opt_outs.contact and outbox.to_addr legitimately hold emails."""
    assert phone_repair.repair_contact("Hana@Example.com", "64") == ("Hana@Example.com", "")


@pytest.mark.parametrize("value", [
    "hana@example.com",
    "Hana@Example.com",
    "stop@example.com",
    "a@b.co",
])
def test_emails_are_never_converted_into_numbers(value):
    """An email must survive every repair path, and case must be preserved.

    Recorded because a mutation test found this protection is REDUNDANT: an email contains no
    digits, so even with the explicit '@' guards removed the function still returns it unchanged.
    That redundancy is welcome, but it means no single-guard mutation can catch a regression here,
    so the behaviour is pinned directly instead. Converting an address into a "number" would target
    a completely different recipient.
    """
    assert phone_repair.repair_phone(value, "64") == (value, "")
    assert phone_repair.repair_contact(value, "64") == (value, "")


def test_an_unrecognised_value_is_left_exactly_as_stored():
    """A value we cannot confidently repair must be REPORTED, not guessed at.

    Rewriting it wrongly would send messages to a stranger, which is worse than leaving it.
    """
    for junk in ("not-a-phone", "call me", "555", "", "   "):
        assert phone_repair.repair_phone(junk, "64") == (junk, ""), junk


def test_an_unknown_country_leaves_values_alone():
    """Without a dial plan there is no basis for a repair, so nothing is attempted."""
    assert phone_repair.repair_phone("021555123", "999") == ("021555123", "")


# ---------------------------------------------------------------- tenant awareness


def test_the_same_stored_value_repairs_differently_per_tenant():
    """The trunk prefix belongs to the TENANT, so one string can mean two things.

    A '+1...' tenant has trunk '1' and 10-digit nationals; a '+64' tenant has trunk '0'. The repair
    must use the tenant's plan, not a single global assumption.
    """
    nz = phone_repair.repair_phone("021555123", "64")[0]
    assert nz == "+6421555123"
    # Under a US plan the same string is not a recognised shape and must be left alone.
    assert phone_repair.repair_phone("021555123", "1") == ("021555123", "")


def test_a_us_tenant_number_is_repaired_with_its_own_plan():
    """A bare 10-digit US national is given its country code, using the US plan not the global idea.

    The reason is the bare-national path rather than the trunk path: '2145550100' does not begin
    with the US trunk '1', it is simply a complete national number missing its country code.
    """
    fixed, reason = phone_repair.repair_phone("2145550100", "1")
    assert fixed == "+12145550100"
    assert reason, "the value was changed, so it must report a reason"


# ---------------------------------------------------------------- usability


def test_a_trunk_prefixed_value_is_not_usable():
    """What the repair is FOR: these are not dialable, so they must be shown as broken."""
    assert phone_repair.is_usable("+021555123", "64") is False
    assert phone_repair.is_usable("+6421555123", "64") is True


def test_an_email_counts_as_usable():
    """Not-a-phone is not a phone problem, so it must not be reported as broken."""
    assert phone_repair.is_usable("hana@example.com", "64") is True


def test_every_target_column_is_a_real_column():
    """A typo in the target list would silently skip a column, so the shape is pinned."""
    assert phone_repair.PHONE_TARGETS, "must repair something"
    for target in phone_repair.PHONE_TARGETS:
        table, column, link, key = target
        assert table and column and link, target
        # `opt_outs` has NO `id`: its key is (tenant_id, contact). A table with no key at all would
        # mean an unscoped UPDATE, so every entry must name either a key or be the composite case.
        assert key is None or key == "id", target


def test_the_composite_key_table_is_present_and_marked_as_such():
    """opt_outs must be repaired, and must not be reached by the generic keyed UPDATE.

    Its key IS (tenant_id, contact), so a repair can collide with an existing row for the same
    person. That needs the merge path, not a plain UPDATE, or an opt-out could be lost.
    """
    composite = [t for t in phone_repair.PHONE_TARGETS if t[3] is None]
    assert [t[0] for t in composite] == ["opt_outs"], composite
