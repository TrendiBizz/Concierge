from app.quotations import clean_lines, json_from_model, measured_lines

CATALOG = [
    {"id": "p1", "name": "Wall cladding (installed)", "unit": "m2", "sale_price_cents": 18500},
    {"id": "p2", "name": "Site visit", "unit": "each", "sale_price_cents": 25000},
]


def test_json_from_model_handles_fences_and_prose():
    assert json_from_model('```json\n{"title": "A"}\n```') == {"title": "A"}
    assert json_from_model('Here you go: {"lines": []} thanks') == {"lines": []}
    assert json_from_model("not json at all") == {}
    assert json_from_model("") == {}


def test_clean_lines_rejects_junk_and_clamps_values():
    lines = clean_lines([
        {"description": "Wall cladding (installed)", "quantity": 12.5, "unit_price_cents": 18500},
        {"description": "   ", "quantity": 1, "unit_price_cents": 100},
        "nope",
        {"description": "Unknown item", "quantity": -3, "unit_price_cents": -99},
        {"description": "Huge", "quantity": 10**9, "unit_price_cents": 10**12},
    ], CATALOG)
    assert len(lines) == 3
    first = lines[0]
    assert first["quantity"] == "12.5"
    assert first["amount_cents"] == 231250
    assert first["product_id"] == "p1"
    unknown = lines[1]
    assert unknown["quantity"] == "0.001"  # clamped, never zero/negative
    assert unknown["unit_price_cents"] == 0
    assert unknown["product_id"] is None
    assert lines[2]["quantity"] == "100000"
    assert lines[2]["unit_price_cents"] == 100_000_000


def test_clean_lines_is_total_on_non_lists():
    assert clean_lines(None, CATALOG) == []
    assert clean_lines({"description": "x"}, CATALOG) == []


def test_measured_lines_uses_net_cladding_area_and_catalogue_price():
    lines = measured_lines({"net_cladding_area_m2": 42.0, "net_wall_area_m2": 60.0}, CATALOG)
    assert len(lines) == 1
    assert lines[0]["quantity"] == "42"
    assert lines[0]["unit_price_cents"] == 18500
    assert lines[0]["product_id"] == "p1"
    assert lines[0]["amount_cents"] == 777000


def test_measured_lines_falls_back_to_net_wall_area_and_works_without_catalogue():
    lines = measured_lines({"net_wall_area_m2": 15}, [])
    assert lines[0]["quantity"] == "15"
    assert lines[0]["unit_price_cents"] == 0


def test_measured_lines_without_measurements():
    assert measured_lines({}, CATALOG) == []
    assert measured_lines(None, CATALOG) == []
