from app import products


def test_view_hides_cost_from_editor():
    row = {"id": "p1", "sku": "DECK-1", "sale_price_cents": 12345, "cost_price_cents": 5000}
    assert "cost_price_cents" not in products.view(row, "editor")
    assert "cost_price_cents" not in products.view(row, "viewer")
    assert products.view(row, "owner")["cost_price_cents"] == 5000
