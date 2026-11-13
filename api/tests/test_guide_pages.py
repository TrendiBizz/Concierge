"""The owner guide is part of the product, so it must render and say the things that matter.

It is public and printable, and it is the only instruction an owner gets for turning a model into a
quote. A broken page or a missing step is a support ticket, so the steps are asserted here.
"""

import asyncio

from app import guides


def page() -> str:
    return asyncio.run(guides.bonsai_cladding_guide()).body.decode()


def test_the_guide_renders_with_a_title():
    html = page()
    assert "<title>Cladding quotes from a 3D model" in html
    assert html.strip().endswith("</html>")


def test_it_names_both_free_programs_and_links_to_them():
    html = page()
    assert "blender.org" in html
    assert "bonsaibim.org" in html


def test_it_covers_the_step_that_makes_a_model_priceable():
    html = page()
    assert "Qto_WallBaseQuantities" in html
    assert "NetSideArea" in html
    assert "IFC4" in html


def test_it_tells_the_owner_where_to_go_in_the_product():
    html = page()
    assert "Designs and CAD" in html
    assert "Price this model" in html
    assert "rate per m²" in html


def test_it_states_the_sanity_check_and_the_limits():
    html = page()
    assert "net cladding area" in html
    assert "PDF and DWG drawings cannot be measured" in html


def test_it_is_printable():
    assert "@media print" in page()
