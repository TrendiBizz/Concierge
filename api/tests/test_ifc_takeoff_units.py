"""Areas from a real model must arrive in square metres, whatever unit the file was authored in.

Bonsai (Blender) writes millimetres by default: a 112.5 m² wall is stored as 112500000. The takeoff
read that number as m², so a cladding quote came out at 112,500,000 m² — about $5 billion. These
tests use a stand-in for ifcopenshell (the real one is a C extension only present in the image) so
the unit arithmetic is pinned without it.
"""

import sys
import types

import pytest

from app import ifc_takeoff


class Entity:
    def __init__(self, kind, **fields):
        self.kind = kind
        self.__dict__.update(fields)
        self.__dict__.setdefault("IsDefinedBy", [])

    def is_a(self, name):
        return self.kind == name


def quantity(name, value, unit=None):
    return Entity("IfcQuantityArea", Name=name, AreaValue=value, Unit=unit)


def wall_with(*quantities):
    qto = Entity("IfcElementQuantity", Quantities=list(quantities))
    rel = Entity("IfcRelDefinesByProperties", RelatingPropertyDefinition=qto)
    return Entity("IfcWall", IsDefinedBy=[rel])


def opening_with(*quantities):
    qto = Entity("IfcElementQuantity", Quantities=list(quantities))
    rel = Entity("IfcRelDefinesByProperties", RelatingPropertyDefinition=qto)
    return Entity("IfcOpeningElement", IsDefinedBy=[rel])


def fake_ifcopenshell(monkeypatch, walls, openings, length_scale):
    """Install a stand-in ifcopenshell whose project unit is `length_scale` metres."""
    model = Entity("model")
    by_kind = {"IfcWall": walls, "IfcWallStandardCase": [], "IfcOpeningElement": openings}
    model.by_type = lambda name: by_kind.get(name, [])

    util_unit = types.SimpleNamespace(calculate_unit_scale=lambda _model: length_scale)
    util = types.SimpleNamespace(unit=util_unit)
    module = types.SimpleNamespace(open=lambda _path: model, util=util)
    monkeypatch.setitem(sys.modules, "ifcopenshell", module)
    monkeypatch.setitem(sys.modules, "ifcopenshell.util", util)
    monkeypatch.setitem(sys.modules, "ifcopenshell.util.unit", util_unit)


def test_millimetre_file_is_converted_to_square_metres(monkeypatch):
    walls = [wall_with(quantity("GrossSideArea", 124_500_000.0),
                       quantity("NetSideArea", 112_500_000.0))]
    fake_ifcopenshell(monkeypatch, walls, [], 0.001)
    result = ifc_takeoff.measure("/tmp/bonsai.ifc")
    assert result["net_wall_area_m2"] == 112.5
    assert result["gross_wall_area_m2"] == 124.5
    assert result["net_cladding_area_m2"] == 112.5
    assert result["unit_area_scale"] == 0.000001


def test_metre_file_is_left_alone(monkeypatch):
    walls = [wall_with(quantity("NetSideArea", 112.5))]
    fake_ifcopenshell(monkeypatch, walls, [], 1.0)
    assert ifc_takeoff.measure("/tmp/metres.ifc")["net_wall_area_m2"] == 112.5


def test_openings_are_converted_too_so_cladding_area_is_right(monkeypatch):
    walls = [wall_with(quantity("NetSideArea", 112_500_000.0))]
    openings = [opening_with(quantity("Area", 6_500_000.0))]
    fake_ifcopenshell(monkeypatch, walls, openings, 0.001)
    result = ifc_takeoff.measure("/tmp/bonsai.ifc")
    assert result["opening_area_m2"] == 6.5
    assert result["net_cladding_area_m2"] == 106.0


def test_an_explicit_square_metre_unit_is_not_scaled_twice(monkeypatch):
    walls = [wall_with(quantity("NetSideArea", 112.5, unit="SQUARE_METRE"))]
    fake_ifcopenshell(monkeypatch, walls, [], 0.001)
    assert ifc_takeoff.measure("/tmp/mixed.ifc")["net_wall_area_m2"] == 112.5


def test_a_model_without_units_is_treated_as_metres(monkeypatch):
    def broken(_model):
        raise RuntimeError("no unit assignment")
    walls = [wall_with(quantity("NetSideArea", 112.5))]
    model = Entity("model")
    model.by_type = lambda name: {"IfcWall": walls, "IfcWallStandardCase": [], "IfcOpeningElement": []}.get(name, [])
    util_unit = types.SimpleNamespace(calculate_unit_scale=broken)
    util = types.SimpleNamespace(unit=util_unit)
    monkeypatch.setitem(sys.modules, "ifcopenshell", types.SimpleNamespace(open=lambda _p: model, util=util))
    monkeypatch.setitem(sys.modules, "ifcopenshell.util", util)
    monkeypatch.setitem(sys.modules, "ifcopenshell.util.unit", util_unit)
    assert ifc_takeoff.measure("/tmp/odd.ifc")["net_wall_area_m2"] == 112.5
