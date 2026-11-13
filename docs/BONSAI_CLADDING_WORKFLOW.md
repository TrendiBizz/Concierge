# Conrad's workflow: Blender + Bonsai → cladding quote

Blender is free. Bonsai is a free Blender add-on for IFC (building) modelling — the only free route
that writes the wall quantities our takeoff reads. No licence cost, no converter.

## One-time install

1. Install **Blender** (blender.org, latest LTS) — free.
2. Install the **Bonsai** add-on (bonsaibim.org / Blender Extensions) — free, open source.
3. In Bonsai preferences check **IFC4** is the schema. Keep units **millimetres** (Bonsai default) —
   our takeoff converts them; do not hand-convert anything.

## Drawing a house for a cladding quote

1. **Project setup**: Bonsai panel → *Project Setup* → set the project unit (millimetre is fine),
   building/site/storey.
2. **Walls**: draw the outside walls, then in Bonsai cast them as **IfcWall** (drawing → *Cast* →
   Wall). Only IfcWall counts in the takeoff — a mesh or a generic blender box does not.
3. **Openings**: doors and windows must be **IfcOpeningElement** voids cut in the wall (drawing →
   *Cast* → Opening). Each opening's area is subtracted from the wall area.
4. **Merge**: run **Merge Walls** on adjacent walls of the same type, so a run of wall is one element
   with one area instead of five fragments.
5. **Quantities** — this is the step that makes the quote work. Bonsai writes
   `Qto_WallBaseQuantities` with `GrossSideArea` (total face) and `NetSideArea` (face minus openings).
   If a wall shows no quantities, add a **Qto Wall Base Quantities** property set to it (Bonsai:
   *Object Properties → Add Quantity* → Wall Base Quantities). Our note "This IFC has no wall area
   quantities" means this step was missed.
6. **Export**: *File → Export → IFC* with schema **IFC4**, and make sure *Element quantities* /
   *Write quantities* is switched on. Name it after the job (`remuera-house.ifc`).

## Quoting it

1. Studio → **Designs and CAD** (under Revenue).
2. **Who is this for?** pick the enquiry or customer.
3. If your rate fields are blank, set them once: **rate per m²**, **waste %**, **minimum charge** →
   *Save rates*.
4. Upload the `.ifc` → **IFC takeoff** → read the numbers (gross, net, openings, net cladding).
5. **Price this model** → a draft quotation appears in **Quotes**, priced at rate × (measured area +
   waste), with the minimum applied if the job is small. Review and send from there.

## Sanity checks before trusting a number

- **Net cladding area** should equal the outside wall area you can physically clad. If it is wildly
  bigger or smaller, the model's units or the opening voids are wrong — fix the model, not the quote.
- The quotation line prints the billed area (measured + waste), e.g. `123.75 m² at $45.00/m²`. If
  that number looks wrong, the model is wrong.
- **Gross** is the whole wall face; **net** is minus openings. Cladding is priced on net.
- A model exported in metres and one exported in millimetres now give the same answer; the takeoff
  records the conversion it applied as `unit_area_scale`.

## What is not covered yet

- Nothing measures from PDF or DWG drawings. If a client sends plans rather than a model, the
  measured m² has to be entered by hand (not built yet — on the outstanding list).
- Windows/doors must be modelled as openings. A door drawn as a textured face will be counted as
  cladding.
