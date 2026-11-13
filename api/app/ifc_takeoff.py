"""Wall-area measurements from an IFC model, in a process that is allowed to die.

ifcopenshell is a C extension and it does not survive every file: a malformed or unusual model
takes the whole interpreter down with a segfault. Reading uploads inside the API process means a
customer's bad export kills the worker serving everyone. So the measuring lives here and is
invoked as `python3 -m app.ifc_takeoff <path>`; a crash then costs one child process and the
caller turns it into a message the customer can act on.

Run directly to see the JSON this prints.
"""

from __future__ import annotations

import json
import sys


def measure(path: str) -> dict:
    """Return wall/opening areas for an IFC file. Raises if the model cannot be read."""
    import ifcopenshell

    model = ifcopenshell.open(path)
    walls = list(model.by_type("IfcWall")) + list(model.by_type("IfcWallStandardCase"))
    gross = net = opening_area = 0.0
    for wall in walls:
        for rel in getattr(wall, "IsDefinedBy", []):
            if not rel.is_a("IfcRelDefinesByProperties"):
                continue
            prop = rel.RelatingPropertyDefinition
            if prop is None or not prop.is_a("IfcElementQuantity"):
                continue
            for quantity in prop.Quantities or []:
                if not quantity.is_a("IfcQuantityArea"):
                    continue
                name = quantity.Name or ""
                value = float(quantity.AreaValue or 0)
                if "GrossSideArea" in name:
                    gross += value
                elif "NetSideArea" in name:
                    net += value
    openings = list(model.by_type("IfcOpeningElement"))
    for opening in openings:
        for rel in getattr(opening, "IsDefinedBy", []):
            if not rel.is_a("IfcRelDefinesByProperties"):
                continue
            prop = rel.RelatingPropertyDefinition
            if prop is None or not prop.is_a("IfcElementQuantity"):
                continue
            for quantity in prop.Quantities or []:
                if quantity.is_a("IfcQuantityArea"):
                    opening_area += float(quantity.AreaValue or 0)
    note = "" if gross or net else (
        "This IFC has no wall area quantities. Measure manually or export quantities from the "
        "authoring tool."
    )
    return {
        "wall_count": len(walls),
        "gross_wall_area_m2": round(gross, 2),
        "net_wall_area_m2": round(net, 2),
        "opening_count": len(openings),
        "opening_area_m2": round(opening_area, 2),
        "net_cladding_area_m2": round(max(net - opening_area, 0), 2) if net else None,
        "note": note,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(json.dumps({"error": "usage: python -m app.ifc_takeoff <path>"}))
        return 2
    try:
        print(json.dumps(measure(argv[1])))
    except Exception as error:  # noqa: BLE001 - any parse failure is reported, not raised
        print(json.dumps({"error": str(error)[:300]}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
