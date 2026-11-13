# Blender + Bonsai is the chosen CAD tool — and its files broke the quote

The decision is **Blender + Bonsai** (free, IFC-native, writes wall quantities). Before writing the
operator guide I checked what a Bonsai file actually does to the takeoff, and the answer was
frightening.

## The fault

Bonsai writes millimetres by default: a 112.5 m² wall is stored as `112500000`. The takeoff read
area values as though they were already square metres:

```
before: {"gross_wall_area_m2": 124500000.0, "net_wall_area_m2": 112500000.0,
         "net_cladding_area_m2": 112500000.0}
```

At $45/m² that is a **$5,062,500,000** quotation. Every IFC produced by the chosen tool would have
produced an absurd number — and it would have looked plausible in the UI as "112.5 million m²".

## Why it slipped through

The earlier test model was hand-built in the IFC4 schema with metre units, so the code path looked
correct. Nobody had fed it a file from the tool the owner will actually use.

## The fix

`app/ifc_takeoff.py` now derives the area scale from the model's project units —
`ifcopenshell.util.unit.calculate_unit_scale(model)` squared — and applies it to wall areas **and**
opening areas. An explicit `Unit = SQUARE_METRE` on a quantity is honoured without double scaling. A
model with no unit assignment is treated as metres. The response carries `unit_area_scale` so the
conversion is visible rather than magic.

```
after: {"wall_count": 1, "unit_area_scale": 1e-06, "gross_wall_area_m2": 124.5,
        "net_wall_area_m2": 112.5, "opening_count": 1, "opening_area_m2": 6.5,
        "net_cladding_area_m2": 106.0}
```

The test model was generated with `ifcopenshell.api` — the same library Bonsai uses internally — so
the fixture matches real Bonsai output, including `Qto_WallBaseQuantities` and an
`IfcOpeningElement`.

## Tests

`api/tests/test_ifc_takeoff_units.py`, five tests against a stand-in ifcopenshell (the real one is a
C extension only present in the image): millimetre → m², metres left alone, openings converted so
net cladding is right, explicit square-metre unit not scaled twice, and a model with no units treated
as metres. Removing the conversion turns two of them red.

Suite: **1063 passed**.

## Operator guide

`docs/BONSAI_CLADDING_WORKFLOW.md` — install, draw walls as IfcWall, cut doors/windows as
IfcOpeningElement, merge wall runs, add Wall Base Quantities, export IFC4 with quantities on, then
Designs → takeoff → *Price this model*.
