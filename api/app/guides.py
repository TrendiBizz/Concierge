"""Owner-facing guides, served by the product itself.

A guide that lives in a file on someone's laptop is not a guide. These pages are public and
printable so an owner can open them from their Concierge link, on a phone, or print them for the
workshop wall. Same words as `docs/BONSAI_CLADDING_WORKFLOW.md`, written for the business owner.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["guides"])

STYLE = """
body{font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
     color:#1a1a1a;max-width:760px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:30px;line-height:1.25;margin:0 0 8px}
h2{font-size:20px;margin:36px 0 8px;padding-top:14px;border-top:1px solid #e6e6e6}
h3{font-size:17px;margin:22px 0 6px}
p,li{color:#333}
.lead{font-size:18px;color:#444}
.step{background:#f6f7f9;border-left:4px solid #2f6fdd;padding:14px 16px;margin:14px 0;border-radius:0 6px 6px 0}
.step strong{display:block;margin-bottom:4px}
.warn{background:#fff7e6;border-left:4px solid #d98200;padding:12px 16px;margin:16px 0;border-radius:0 6px 6px 0}
code{background:#eef0f3;padding:1px 5px;border-radius:3px;font-size:14px}
a{color:#2f6fdd}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:15px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #e6e6e6}
footer{margin-top:48px;padding-top:16px;border-top:1px solid #e6e6e6;color:#666;font-size:14px}
@media print{body{padding:0;max-width:none}.no-print{display:none}a{color:#1a1a1a;text-decoration:none}}
"""


@router.get("/guide/bonsai-cladding", response_class=HTMLResponse, include_in_schema=False)
async def bonsai_cladding_guide():
    """How a cladding business turns a 3D model into a priced quote."""
    return HTMLResponse(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cladding quotes from a 3D model — Concierge</title>
<style>{STYLE}</style>
</head>
<body>
<h1>Cladding quotes from a 3D model</h1>
<p class="lead">Draw the house once in a free CAD program. Concierge measures the outside clad area,
subtracts the windows and doors, adds your waste, and prices it at your rate per square metre. You
review the quote and send it.</p>

<h2>What you need (both free)</h2>
<table>
<tr><th>Software</th><th>What it is for</th><th>Cost</th></tr>
<tr><td><a href="https://www.blender.org/download/">Blender</a></td><td>The 3D program</td><td>Free</td></tr>
<tr><td><a href="https://bonsaibim.org/">Bonsai</a></td><td>A free add-on that makes Blender understand buildings (IFC)</td><td>Free</td></tr>
</table>
<p>Bonsai is what makes the numbers work: it writes the wall areas Concierge reads. A model drawn in
Blender alone has no wall areas, and there will be nothing to price.</p>

<h2>1. Install Blender and Bonsai (once, about 15 minutes)</h2>
<div class="step"><strong>1a. Install Blender</strong>
Download from blender.org and run the installer. Accept the defaults.</div>
<div class="step"><strong>1b. Add Bonsai</strong>
In Blender: <em>Edit → Preferences → Get Extensions</em>, search <strong>Bonsai</strong>, click Install,
then tick it to enable. A "Bonsai" tab appears in the 3D viewport sidebar (press <code>N</code> if you
cannot see it).</div>
<div class="step"><strong>1c. Check the schema</strong>
In Bonsai preferences make sure the schema is <strong>IFC4</strong>. Leave the units on
<strong>millimetres</strong> — that is Bonsai's default and Concierge converts them automatically.</div>

<h2>2. Draw the house</h2>
<div class="step"><strong>2a. Start a project</strong>
Bonsai panel → <em>Project Setup</em>. Set the project unit, then add a site, building and storey.</div>
<div class="step"><strong>2b. Draw the outside walls</strong>
Draw the wall lines, then cast them as walls: <em>Drawing → Cast → Wall</em>. Walls must be
<strong>IfcWall</strong> — a plain Blender cube is ignored by the takeoff.</div>
<div class="step"><strong>2c. Cut the windows and doors</strong>
Draw each opening and cast it as an <em>Opening</em> (<em>Drawing → Cast → Opening</em>). These areas
are subtracted from the cladding. A door painted onto a wall face is counted as cladding, so cut it
properly.</div>
<div class="step"><strong>2d. Merge wall runs</strong>
Select the walls of one type and run <em>Merge Walls</em>, so a long run is one element with one
area rather than five fragments.</div>
<div class="step"><strong>2e. Add the wall quantities — this is the step that makes it priceable</strong>
Each wall needs its base quantities (Qto). In the object properties, add
<strong>Qto_WallBaseQuantities</strong>. Bonsai fills <code>GrossSideArea</code> (whole face) and
<code>NetSideArea</code> (face minus openings). If you skip this, Concierge will tell you the model has
no wall area quantities instead of guessing.</div>

<h2>3. Export and upload</h2>
<div class="step"><strong>3a. Export</strong>
<em>File → Export → IFC</em>, schema <strong>IFC4</strong>, with <em>write quantities</em> switched on.
Name it after the job, e.g. <code>remuera-house.ifc</code>.</div>
<div class="step"><strong>3b. Upload</strong>
In Concierge open <strong>Designs and CAD</strong> (under Revenue), choose the customer under
<em>Who is this for?</em>, then upload the IFC and press <strong>IFC takeoff</strong>.</div>

<h2>4. Price it</h2>
<div class="step"><strong>4a. Set your rate once</strong>
On the same screen, under <em>How your quotes are worked out</em>, enter your <strong>rate per m²</strong>,
your <strong>waste %</strong> and your <strong>minimum charge</strong>, then save. These are your numbers —
nobody else's quote uses them.</div>
<div class="step"><strong>4b. Price the model</strong>
Press <strong>Price this model</strong>. Concierge measures the outside clad area, subtracts openings,
adds your waste, multiplies by your rate, applies your minimum if the job is small, adds GST, and
saves a <strong>draft quotation</strong> against the customer.</div>
<div class="step"><strong>4c. Review and send</strong>
Open <strong>Quotes</strong>. Check the line: it shows the billed area, e.g.
<em>123.75 m² at $45.00/m²</em>. Edit if you want, then send it to the customer.</div>

<h2>Checking a number before you trust it</h2>
<div class="warn"><strong>The sanity check that matters</strong>
Does the <em>net cladding area</em> match what you could physically clad? If it is wildly high or low,
the model is wrong — fix the model, not the quote. The two usual causes are walls not cast as IfcWall,
and openings not cut as IfcOpeningElement.</div>
<ul>
<li><strong>Gross</strong> is the whole wall face; <strong>net</strong> is minus the openings. Cladding is
priced on net.</li>
<li>Millimetres and metres give the same answer. The takeoff tells you the conversion it applied.</li>
<li>If the app says the model has no wall area quantities, step 2e was missed.</li>
</ul>

<h2>Not covered yet</h2>
<ul>
<li>PDF and DWG drawings cannot be measured automatically. If a client sends plans instead of a model,
the square metres have to be entered by hand.</li>
<li>Only walls and openings are measured. Roofs, soffits and flashings are not priced by this yet.</li>
</ul>

<footer>
<p class="no-print">Concierge — cladding quotes from a measured model. This page can be printed
(⌘/Ctrl + P) or saved as a PDF to keep in the workshop.</p>
</footer>
</body>
</html>""")
