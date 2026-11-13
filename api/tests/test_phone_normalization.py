"""Phone normalisation.

`normalize_phone` decides which E.164 number we text, book against, unsubscribe and merge customer
identities on. Getting it wrong is not cosmetic: a wrong number means a message to a stranger, a
booking on the wrong customer, or one person split across two records.

Three defects this pins down, all of which shipped:

  1. A national trunk prefix was never stripped, so `021555123` became `+021555123` and
     `09 555 1234` became `+095551234` -- numbers that cannot exist.
  2. A bare national number had the country code glued on WITHOUT removing the leading digit it
     replaced: `6421555123` became `+646421555123`, with the country code doubled.
  3. The 10-digit branch assumed US semantics, so under a New Zealand tenant `2145550100` became
     `+642145550100` -- silently relocating a US number to New Zealand.

The rule the implementation now follows: only produce a number when the input is unambiguously
interpretable. Stripping a trunk prefix and applying the tenant's country code is well defined;
guessing what a bare 7-9 digit string means is not. Returning None is the correct answer for an
ambiguous input, because the alternative is texting the wrong person.
"""
import pytest

from app.contact import contact_key, normalize_phone


# ---------------------------------------------------------------- already international

def test_international_form_is_preserved():
    """A number written with + is already unambiguous and must pass through unchanged."""
    assert normalize_phone("+6421555123") == "+6421555123"
    assert normalize_phone("+1 214 555 0100") == "+12145550100"
    assert normalize_phone("+44 7700 900123") == "+447700900123"
    assert normalize_phone("+64 21 555 123") == "+6421555123"


def test_international_form_ignores_the_country_code_argument():
    """The explicit + wins over the tenant setting; otherwise a caller could rewrite a real number."""
    assert normalize_phone("+12145550100", "64") == "+12145550100"
    assert normalize_phone("+6421555123", "1") == "+6421555123"


# ---------------------------------------------------------------- trunk prefixes

@pytest.mark.parametrize("raw", ["021555123", "021 555 123", "021-555-123", "(021) 555 123"])
def test_new_zealand_mobile_trunk_zero_is_stripped(raw):
    """021... is a national format: the leading 0 is a trunk prefix, not part of the number."""
    assert normalize_phone(raw, "64") == "+6421555123"


@pytest.mark.parametrize("raw", ["095551234", "09 555 1234", "(09) 555-1234"])
def test_new_zealand_landline_trunk_zero_is_stripped(raw):
    assert normalize_phone(raw, "64") == "+6495551234"


def test_uk_trunk_zero_is_stripped():
    """07700900123 is the UK national format for +447700900123."""
    assert normalize_phone("07700900123", "44") == "+447700900123"


def test_trunk_prefix_is_not_stripped_for_a_country_without_one():
    """Removing a leading digit is only safe where that digit is a trunk prefix.

    For a +1 tenant a 10-digit number is already complete, so no digit may be removed.
    """
    assert normalize_phone("2145550100", "1") == "+12145550100"


# ---------------------------------------------------------------- no doubled country code

def test_bare_number_with_country_code_already_present_is_not_doubled():
    """The bug: 6421555123 under +64 became +646421555123.

    A national-only mobile is written WITHOUT its trunk zero as 21555123, but people also type the
    country code and then the number as it appears locally. Neither may produce a doubled prefix.
    """
    assert normalize_phone("6421555123", "64") != "+646421555123"
    assert normalize_phone("6421555123", "64") == "+6421555123"


def test_us_number_with_a_leading_country_code_one():
    # A country code is now required rather than assumed: without one we cannot tell a US number
    # from a New Zealand one, and inventing "+1" is what produced +10278817368 for a NZ mobile.
    assert normalize_phone("1 214 555 0100", "1") == "+12145550100"
    assert normalize_phone("12145550100", "1") == "+12145550100"


# ---------------------------------------------------------------- never invent a number


def test_short_input_is_rejected():
    """Too short to be a real subscriber number; must not be turned into a guess."""
    assert normalize_phone("123") is None
    assert normalize_phone("") is None
    assert normalize_phone("   ") is None


def test_a_bare_national_number_without_its_trunk_zero_is_accepted():
    """'21555123' is the NZ national mobile written without its trunk zero, so it IS usable.

    This was originally written as a refusal case and was wrong: an NZ mobile has 8 significant
    digits after the trunk 0 is removed, so 21555123 is complete and unambiguous. All the spellings
    below are the same number.
    """
    assert normalize_phone("21555123", "64") == "+6421555123"
    assert normalize_phone("95551234", "64") == "+6495551234"


def test_a_digit_count_that_matches_no_national_length_is_refused():
    """Lengths the country cannot have are refused, rather than forced into a form.

    NZ national numbers are 8 or 9 digits, so 10 or more is not one. This is the case a mutation
    test caught the suite failing to pin: a guessing implementation returns a number for these.
    """
    for raw in ("1234567890", "12345678901", "123456789012"):
        assert normalize_phone(raw, "64") is None, raw


def test_a_number_longer_than_e164_allows_is_refused():
    assert normalize_phone("1234567890123456", "64") is None


def test_an_eight_digit_nz_number_is_ACCEPTED_even_though_it_could_be_anything():
    """An honest boundary, documented rather than pretended away.

    An 8-digit string IS a valid NZ national length, so '+6412345678' is a legitimate reading and
    the function accepts it. Nothing local can distinguish a real number from a random 8-digit run
    without a prefix table, which is a deliberate omission: the accepted lengths are the guard, and
    callers must still confirm a number before relying on it.
    """
    assert normalize_phone("12345678", "64") == "+6412345678"


def test_input_too_short_for_any_national_number_is_refused_rather_than_guessed():
    """Below the shortest national length there is nothing to complete.

    Guessing would risk texting a stranger, so these return None instead.
    """
    for raw in ("555123", "555 1234", "2155", "21555"):
        assert normalize_phone(raw, "64") is None, raw


def test_letters_do_not_become_numbers():
    """Non-digits must not be silently dropped into something dialable."""
    assert normalize_phone("not-a-phone", "64") is None
    assert normalize_phone("call me", "64") is None


def test_too_long_input_is_rejected():
    """E.164 caps at 15 digits; anything longer cannot be a phone number."""
    assert normalize_phone("+1234567890123456", "1") is None


def test_a_plus_with_nothing_usable_is_rejected():
    assert normalize_phone("+", "64") is None
    assert normalize_phone("+  ", "64") is None


# ---------------------------------------------------------------- the original contract

def test_original_us_mobile_passes_through_the_10_digit_branch():
    """Regression guard on the documented behaviour test_units.py asserts."""
    assert normalize_phone("214-555-0100", "1") == "+12145550100"
    assert normalize_phone("(214) 555-0100", "1") == "+12145550100"


# ---------------------------------------------------------------- contact_key consistency


def test_contact_key_agrees_with_normalize_phone_for_a_local_number():
    """Opt-out keys and identity keys must not disagree about the same person.

    If contact_key stored a trunk-prefixed form while normalize_phone produced the real number, an
    opt-out would fail to match and we would text someone who had unsubscribed.
    """
    assert contact_key("021555123", "64") == normalize_phone("021555123", "64")
    assert contact_key("21 555 123", "64") == contact_key("+6421555123", "64")


def test_contact_key_still_canonicalises_email():
    assert contact_key("Pat@Example.COM") == "pat@example.com"


def test_contact_key_falls_back_to_the_raw_value_when_unparseable():
    """An unparseable contact must still get a stable key, or opt-outs could never be recorded."""
    assert contact_key("not-a-phone", "64") == "not-a-phone"


def test_two_spellings_of_one_customer_share_a_key():
    """The identity guarantee the case timeline depends on."""
    for raw in ("+6421555123", "021555123", "6421555123", "021 555 123"):
        assert contact_key(raw, "64") == "+6421555123", raw


# ---------------------------------------------------------------- opt-out round trip (real DB)
#
# The unit tests above prove normalize_phone/contact_key in isolation. These prove the property that
# actually matters legally: an opt-out recorded in one spelling must suppress every spelling, and it
# must be keyed with the TENANT's dialling country, not the global default.

import asyncio
import os
import pathlib

import asyncpg

from app import db as _db, outbox

_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _dsn():
    port = os.environ.get("CONCIERGE_TEST_POSTGRES_PORT", "55432")
    return f"postgresql://postgres:test@127.0.0.1:{port}/postgres"


def _run(coro):
    asyncio.set_event_loop(_LOOP)
    return _LOOP.run_until_complete(coro)


async def _make_tenant(pool, slug, name, key, cc):
    return await pool.fetchval(
        "insert into tenants(slug,name,public_key,default_country_code) values($1,$2,$3,$4) returning id",
        slug, name, key, cc)


@pytest.fixture()
def real_db():
    schema = (pathlib.Path(__file__).parent.parent / "app" / "schema.sql").read_text().replace("__DIM__", "384")

    async def connect():
        return await asyncpg.create_pool(_dsn(), min_size=1, max_size=4, timeout=5, loop=_LOOP)

    try:
        pool = _run(connect())
    except Exception as exc:  # noqa: BLE001 - no database here
        pytest.skip(f"No test PostgreSQL available: {exc}")

    async def setup():
        async with pool.acquire() as c:
            await c.execute("drop schema if exists public cascade; create schema public")
            await c.execute(schema)

    _run(setup())
    previous = _db._pool
    _db._pool = pool
    yield pool
    _db._pool = previous
    _run(pool.close())


def test_opt_out_is_stored_canonical_and_matches_every_spelling(real_db):
    """Regression: the opt-out was stored RAW for non-US numbers, so other spellings still sent.

    Before the fix, opting out with '021555123' stored that literal string, and every other spelling
    of the same number failed to match it -- we would have kept texting someone who unsubscribed.
    """
    tid = _run(_make_tenant(real_db, "nz", "NZ", "pk1", "64"))
    _run(outbox.opt_out(tid, "021555123"))
    assert _run(real_db.fetchval("select contact from opt_outs where tenant_id=$1", tid)) == "+6421555123"
    for spelling in ("+6421555123", "6421555123", "021 555 123", "21555123", "021555123"):
        assert _run(outbox.is_opted_out(tid, spelling)) is True, spelling
    assert _run(outbox.is_opted_out(tid, "+6421555999")) is False


def test_opt_in_clears_the_opt_out_in_any_spelling(real_db):
    """START must work even when the customer types a different format from their STOP."""
    tid = _run(_make_tenant(real_db, "nz", "NZ", "pk1", "64"))
    _run(outbox.opt_out(tid, "021555123"))
    _run(outbox.opt_in(tid, "021 555 123"))
    assert _run(outbox.is_opted_out(tid, "+6421555123")) is False


def test_us_tenant_is_unaffected_by_trunk_prefix_handling(real_db):
    """The fix must not remove a leading digit where no trunk prefix exists."""
    tid = _run(_make_tenant(real_db, "us", "US", "pk2", "1"))
    _run(outbox.opt_out(tid, "2145550100"))
    assert _run(real_db.fetchval("select contact from opt_outs where tenant_id=$1", tid)) == "+12145550100"
    assert _run(outbox.is_opted_out(tid, "+1 214 555 0100")) is True


def test_two_tenants_do_not_share_opt_outs(real_db):
    """Opt-outs are tenant-scoped: one business unsubscribing must not mute another's customer."""
    nz = _run(_make_tenant(real_db, "nz", "NZ", "pk1", "64"))
    us = _run(_make_tenant(real_db, "us", "US", "pk2", "1"))
    _run(outbox.opt_out(nz, "+6421555123"))
    assert _run(outbox.is_opted_out(us, "+6421555123")) is False
