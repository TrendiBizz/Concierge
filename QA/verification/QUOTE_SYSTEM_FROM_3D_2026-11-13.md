# A quotation system per business, priced from the 3D model

The 3D capability was hidden and had no link to money. It is now a quoted, priced, saved quotation
against a real customer, and it is reachable from where owners already work.

## What was missing

`Designs and CAD` could measure an IFC but the only "quote" it produced was an unsaved, AI-drafted
line based on a **product** price — not a rate per square metre. Nothing let a cladding contractor
say "my rate is $45/m², add 10% waste, minimum $500", and nothing turned that into a saved quote
against a customer. The tab also sat under *Marketing*, where a trades owner would never look for it.

## What now exists

**A quoting method per business** (`quote_profiles`): name, rate per m², waste %, minimum charge,
which measurement to use (net clad area / net wall / gross wall), currency and GST rate. Multiple
methods are allowed; one is the default. This is per tenant, so Conrad's cladding business and every
other customer price differently from the same software.

**A saved quotation from a measured model** (`POST /owner/designs/{id}/quote`): pick a customer,
press *Price this model*, and the measured area is multiplied out and stored as a **draft quotation**
in the CRM — ready to review and send, not sent automatically.

**Discoverability**: *Designs and CAD* now sits under **Revenue**, directly below Quotes. The Quotes
screen opens with a card explaining the measured-model route and a button straight into it. Designs
opens with "Who is this for?" (the customer picker), then "How your quotes are worked out" (the
rate), then upload/view, and every priced model ends with *Open Quotes to review or send it*.

## Proof, run live against a real IFC

```
upload     remuera-house.ifc            -> 201
takeoff    net_cladding_area_m2         -> 112.5 m² (1 wall)
rate       $45.00/m², 10% waste, $500 minimum
quote      "Nu-Wall cladding — 123.75 m² at $45.00/m²"
           subtotal $5,568.75 + GST $835.31 = $6,404.06
           contact Jane Remuera · phone +64215550188 · status draft
note       "10% waste added to the measured area (112.5 m² measured)."
```

Maths check: 112.5 × 1.10 = 123.75 m², × $45.00 = $5,568.75, GST 15% = $835.31, total $6,404.06.

Eight unit tests pin the arithmetic (`api/tests/test_quote_profiles_pricing.py`): area × rate, waste
applied to billed area only, minimum charge winning on small jobs and *not* reducing big ones,
half-up rounding to the cent, measurement selection, refusal when the model lacks that area, and a
zero rate still producing a line for the owner to price.

## Faults found and fixed on the way

1. **I broke the API.** Adding the router registration without the import raised `NameError` at
   module load: the container restarted in a loop and the product was down for ~4 minutes. Fixed the
   import; new guard test imports `app.main` and asserts the routes appear in the OpenAPI paths
   (mutation-checked: removing the import turns it red).
2. **`Decimal` was used but never imported** in `designs.py`, so every priced quote returned 500.
   Caught by the existing undefined-names guard once it ran over the new code; fixed and the full
   suite passes.
3. **Waste printed as "1E+1%"** — `Decimal.normalize()` produced scientific notation in a note that
   goes on a customer's quotation. Now formatted as a plain number, with a test.

Suite: **1058 passed**. Walkthrough records (profile, design, lead, quotation) deleted afterwards;
`profiles 0, designs 0`.

## Outstanding, by design

- **The rate is the owner's number, not ours.** The system ships with the rate empty and the field to
  set it — we do not invent a price.
- Only the IFC path measures automatically. DWG/STEP/3DM still upload and store without measurement.
