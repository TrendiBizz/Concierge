# Designs and CAD: checked, and it was broken

The operator asked for the 3D CAD software to be checked. It lives in Studio → **Designs and CAD**
(embed of the `online-3d-viewer` engine, plus IFC wall-area takeoff feeding quotations). I walked it
as an owner and as a customer. **The 3D viewer did not work at all**, and a second defect could take
the API down.

## What was broken

### 1. Every 3D model failed to open — "No importable file found."

The tab fetched the file, wrapped it in a `blob:` URL and handed that to the viewer. A blob URL
carries no filename, so the engine could not tell an STL from a PDF and refused every model. Measured
on a valid ASCII STL cube: the viewer panel printed exactly `No importable file found.` with a
canvas present and no error.

**Fix.** Fetch the blob, wrap it in a `File` carrying the original `design.filename`, and call
`LoadModelFromFileList([file])`. The engine then picks the importer from the real extension.

**Proof.** After the fix the same cube renders in the 520px panel (screenshot
`/tmp/walk10/cad_fixed.png`), `No importable file found` is gone, 0 JS errors.

### 2. "Copy" claimed success when the browser refused

"Create upload link" called `navigator.clipboard.writeText(...)` without awaiting it, then set the
status to *"Upload link created and copied."* The promise rejects when the browser withholds
clipboard permission — an uncaught error in the console and a **false claim** to the owner, who then
pastes nothing. The same pattern sat in "Copy embed code" and "Copy link".

**Fix.** A shared `copyText()` helper that awaits the call and returns whether it worked; the three
call sites now say "copied" only when it was, and otherwise tell the owner to copy it manually.

**Proof.** Clicking "Create upload link" with the clipboard unavailable now reports *"Upload link
created — copy it below."* with no uncaught error.

### 3. A customer's IFC could kill the API process

`ifcopenshell` is a C extension and it segfaults the interpreter on files it cannot handle. The
takeoff measure ran **inside the API process** (in a thread), so one bad export took down the worker
serving every other customer — an outage caused by an upload.

Reproduced: a small, syntactically plausible but semantically incomplete IFC caused `Segmentation
fault (core dumped)` when measured in-process.

**Fix.** The measuring moved to `app/ifc_takeoff.py` and is invoked as a child process
(`python3 -m app.ifc_takeoff <path>`) with a 120s timeout. A crash now costs one child; the endpoint
turns it into a 422 that says the file crashed the reader and to re-export as IFC4.

**Proof.** The same malformed file, through the child, kills only the child; the API stays
`healthy`. A valid IFC measures correctly:
`{"wall_count": 1, "gross_wall_area_m2": 24.5, "net_wall_area_m2": 22.0, "opening_count": 1,
"opening_area_m2": 1.5, "net_cladding_area_m2": 20.5}`.
Five tests in `api/tests/test_ifc_takeoff_is_crash_safe.py`; mutating the fix (an in-process
`import ifcopenshell`) turns all five red.

## What worked, verified end to end

| Step | Result |
|---|---|
| Upload an STL from the Designs tab | `benchtop-test.stl uploaded.`, appears in the list with size and date |
| View it | 3D canvas 789×520, WebGL active, model visible, "Close viewer" works |
| View a non-3D file (PDF/plan) | opens in a new tab instead of the viewer (code path) |
| Download | saves the original file |
| "Create upload link" | link `…/upload/<token>`, expires 7 days |
| Customer opens the upload page | "Send your plans" → choose file → **"Thank you. Your plans were received."** |
| IFC takeoff | correct gross/net/opening areas and net cladding area |
| Console | 0 JS errors, 0 5xx on our endpoints |

Test designs and upload links were deleted afterwards (`designs_left: 0`). Suite: **1049 passed**.

## Still unverified / product notes

- **3D is a viewer, not a CAD editor.** It renders and measures; it does not let the owner edit
  geometry. If "3D CAD software" was expected to draw or modify models, that is a product decision,
  not a bug — the tab says "Upload plans or 3D models, view them, and read wall areas from IFC
  models for cladding quotes."
- **DWG/DXF/3DM/STEP** are accepted for upload but have no viewer or takeoff path; they are stored
  and downloadable only. STEP and DWG conversion would need a converter service.
- Takeoff reads `IfcQuantityArea` names `GrossSideArea`/`NetSideArea`. Models that export different
  quantity names report "no wall area quantities" with a clear note rather than a wrong number.
