# Onboarding Conrad (operator checklist)

What the operator does, what Conrad does, and what to check before you hand it over.
Guide the customer reads: **https://concierge.trendibizz.com/guide/bonsai-cladding** (public,
printable — the same steps are also in-app, on the Designs and CAD screen under "New to this?").

## 1. Account — operator

- [ ] Tenant exists: `pukeko-construction` (Pukeko Construction).
- [ ] Owner login is currently **`pukeko-demo@trendibizz.com`** — a demo address. Change it to
      Conrad's real email before he uses it (`tenant_users.email`), or re-invite with it.
- [ ] Mint his sign-in link:
      `POST /admin/tenants/pukeko-construction/owner-recovery` with `X-Admin-Token`
      (from `/opt/trendi/shared/api.env`). Returns `invitation_url` → send that to Conrad.
      The link is single-use and lands him in Studio already signed in.
- [ ] Never email or text a link from a test script; send it yourself.

## 2. Quoting method — already created, needs his numbers

A default method called **Nu-Wall cladding** exists for his tenant:

| Field | Value now | Who sets it |
|---|---|---|
| Rate per m² | **$0 (empty on purpose)** | Conrad — his price |
| Waste % | 10 | Conrad |
| Minimum charge | $0 | Conrad |
| Measured area | outside clad area net of openings | us |
| GST | 15% | us |

He sets the three numbers once in **Designs and CAD → How your quotes are worked out → Save rates**.
Do not fill in a rate for him: it is his commercial decision and it will end up on a customer's quote.

## 3. First run-through with him (15 minutes, screenshare)

1. Open https://concierge.trendibizz.com/guide/bonsai-cladding together and leave it with him.
2. Install Blender + Bonsai (free) on his machine while he watches.
3. Draw one simple wall, cast it as a wall, cut one opening, add `Qto_WallBaseQuantities`.
4. Export IFC4, upload it in **Designs and CAD**, press **IFC takeoff**.
5. Read the numbers together: gross, net, openings, **net cladding area**.
6. Press **Price this model** after picking an enquiry → open **Quotes** → show him the draft line
   (`123.75 m² at $45.00/m²`) and how to send it.
7. Tell him the sanity rule: if net cladding area is not what he could physically clad, the model is
   wrong — fix the model, not the quote.

## 4. Before you call it done

- [ ] He has signed in with his own email and seen his own tenant (not the demo).
- [ ] His rate/waste/minimum are saved and a test quote shows a plausible total.
- [ ] He knows the guide link, and that it prints.
- [ ] You have told him what is **not** covered yet: PDF/DWG plans must be measured by hand, and only
      walls/openings are priced — no roofs, soffits or flashings.

## Known limits to state plainly

- No hand-entry of m² yet; a job without a 3D model cannot be quoted in the product.
- Windows/doors must be modelled as openings, or they are counted as cladding.
