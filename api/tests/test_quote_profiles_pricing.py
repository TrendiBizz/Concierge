"""A measured model has to become the right money, every time.

The pricing maths is pure on purpose: these tests pin the arithmetic that a cladding quote depends
on (rate per square metre, waste, minimum charge, rounding) without a database or a browser.
"""

from decimal import Decimal

import pytest

from app.quote_profiles import compute_quote


def profile(**overrides):
    base = {'name': 'Nu-Wall cladding', 'unit': 'm²', 'rate_cents': 4500,
            'waste_percent': Decimal('0'), 'minimum_cents': 0,
            'measurement': 'net_cladding', 'currency': 'NZD'}
    base.update(overrides)
    return base


TAKEOFF = {'net_cladding_area_m2': 20.5, 'net_wall_area_m2': 22.0, 'gross_wall_area_m2': 24.5}


def test_area_times_rate():
    result = compute_quote(profile(), TAKEOFF)
    assert result['measured_area'] == '20.50'
    assert result['amount_cents'] == 92250  # 20.5 m² × $45.00
    assert result['line']['unit_price_cents'] == 4500
    assert '20.50 m²' in result['line']['description']


def test_waste_is_added_to_the_billed_area_not_the_measured_one():
    result = compute_quote(profile(waste_percent=Decimal('10')), TAKEOFF)
    assert result['measured_area'] == '20.50'
    assert result['billed_area'] == '22.55'
    assert result['amount_cents'] == 101475  # 22.55 × 4500
    assert any('10%' in note for note in result['notes'])


def test_minimum_charge_wins_on_small_jobs_and_says_so():
    result = compute_quote(profile(minimum_cents=50000), {'net_cladding_area_m2': 2})
    assert result['amount_cents'] == 50000
    assert any('Minimum charge' in note for note in result['notes'])


def test_minimum_does_not_reduce_a_bigger_job():
    result = compute_quote(profile(minimum_cents=50000), TAKEOFF)
    assert result['amount_cents'] == 92250
    assert not result['notes']


def test_rounding_is_half_up_to_the_cent():
    # 20.55 × 1234 = 25358.7 -> 25359
    result = compute_quote(profile(rate_cents=1234), {'net_cladding_area_m2': 20.55})
    assert result['amount_cents'] == 25359


def test_gross_wall_measurement_is_selectable():
    result = compute_quote(profile(measurement='gross_wall'), TAKEOFF)
    assert result['measured_area'] == '24.50'


def test_a_model_without_the_needed_area_is_refused_not_guessed():
    with pytest.raises(ValueError) as caught:
        compute_quote(profile(), {'gross_wall_area_m2': 24.5})
    assert 'nothing to price' in str(caught.value)


def test_zero_rate_still_produces_a_line_for_the_owner_to_price():
    result = compute_quote(profile(rate_cents=0), TAKEOFF)
    assert result['amount_cents'] == 0
    assert result['line']['quantity'] == '20.50'
