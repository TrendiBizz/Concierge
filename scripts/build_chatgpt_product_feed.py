#!/usr/bin/env python3
"""Build the ChatGPT Business Hub product feed for trendibizz.com.

Writes:
  website/chatgpt-products.csv            hosted at https://trendibizz.com/chatgpt-products.csv
  website/brand/products/<item>.png       one 1200x1200 PNG per product (direct JPEG/PNG links only)

Rules from the Rankability / ChatGPT Business Hub kit that this enforces:
  * UTF-8 CSV, header row, one product per row, the nine required columns.
  * price = number, space, currency code ("250.00 USD"); availability from the five allowed values.
  * empty cell instead of a placeholder; every link is a full https address.
  * descriptions use ONLY wording from the live site (no invented features, limits or prices).
  * products without a listed price (penetration testing: "quoted on enquiry") are left out.

Run:  python3 scripts/build_chatgpt_product_feed.py            (needs Pillow for the images)
      python3 scripts/build_chatgpt_product_feed.py --check    (validate the CSV only, no writes)
Prices must be changed here AND on the site; the check mode compares nothing live, so re-run the
live verification in QA/verification/CHATGPT_BUSINESS_HUB_KIT.md after every price change.
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "website"
CSV_PATH = SITE / "chatgpt-products.csv"
IMG_DIR = SITE / "brand" / "products"
BASE = "https://trendibizz.com"

COLUMNS = [
    "item_id", "title", "description", "url", "brand", "seller_name", "image_url", "availability",
    "price", "condition", "product_category", "is_digital", "seller_url", "seller_tos",
    "seller_privacy_policy",
]
REQUIRED = COLUMNS[:9]
AVAILABILITY = {"in_stock", "out_of_stock", "pre_order", "backorder", "unknown"}

CONCIERGE_CORE = (
    "Concierge is an AI receptionist for small business. It answers from your own website and "
    "business information, captures contact details and records every enquiry in a built-in CRM. "
    "It includes agreed appointment times, booking records and follow-up tasks, new-enquiry alerts "
    "to the email and phone you nominate, website chat added with one line of code, and a private "
    "portal with owner, editor and viewer roles. Setup, knowledge import from your website and "
    "channel testing are part of onboarding. There is no per-call or per-minute charge from Trendi; "
    "a phone number or SMS provider, if you use one, is billed separately. Prices are in USD. "
    "Trendi does not promise leads or sales."
)

PRODUCTS = [
    {
        "item_id": "trendi-concierge-monthly",
        "title": "Trendi Concierge - AI Receptionist, Monthly Subscription",
        "description": CONCIERGE_CORE + " Monthly plan: 3-month minimum, then it renews monthly.",
        "url": f"{BASE}/concierge",
        "price": "250.00 USD",
        "headline": "Concierge",
        "sub": "AI receptionist - monthly",
        "price_label": "USD $250 / month",
    },
    {
        "item_id": "trendi-concierge-yearly",
        "title": "Trendi Concierge - AI Receptionist, Yearly Subscription",
        "description": CONCIERGE_CORE + " Yearly plan: available after your first three months, 15% off "
                       "the monthly price, one payment a year.",
        "url": f"{BASE}/ai-receptionist-cost",
        "price": "2550.00 USD",
        "headline": "Concierge",
        "sub": "AI receptionist - yearly",
        "price_label": "USD $2,550 / year",
    },
    {
        "item_id": "trendi-seo-ai-visibility-monthly",
        "title": "Trendi SEO and AI Visibility - Done-for-You Monthly Service",
        "description": (
            "Done-for-you SEO and AI visibility for businesses worldwide: work to make your site "
            "Indexed, Found and Mentioned, with mentions and links logged separately. Includes AI "
            "mention tracking across ChatGPT, Perplexity, Gemini and Claude, keyword research and a "
            "search map for every page, in-depth articles each month, comparison and alternatives "
            "pages, page fixes (titles, copy, speed and internal links), index checks, fact checks so "
            "your prices and features are right everywhere, and a short report every week. "
            "3-month minimum, then month to month. Not included: ranking or AI-mention guarantees, "
            "a penetration test or security audit, paid ads management, or website redesign. "
            "Prices are in USD."
        ),
        "url": f"{BASE}/seo",
        "price": "1500.00 USD",
        "headline": "SEO + AI visibility",
        "sub": "Done for you - monthly",
        "price_label": "USD $1,500 / month",
    },
]


def row(p: dict) -> dict:
    return {
        "item_id": p["item_id"], "title": p["title"], "description": p["description"], "url": p["url"],
        "brand": "Trendi", "seller_name": "Trendi",
        "image_url": f"{BASE}/brand/products/{p['item_id']}.png",
        "availability": "in_stock", "price": p["price"], "condition": "new",
        "product_category": "Software", "is_digital": "true", "seller_url": BASE,
        "seller_tos": f"{BASE}/terms", "seller_privacy_policy": f"{BASE}/privacy",
    }


def validate(rows: list[dict]) -> list[str]:
    problems = []
    seen = set()
    for r in rows:
        who = r.get("item_id") or "<row>"
        for col in REQUIRED:
            if not (r.get(col) or "").strip():
                problems.append(f"{who}: required column {col} is empty")
        if r["item_id"] in seen:
            problems.append(f"{who}: duplicate item_id")
        seen.add(r["item_id"])
        if len(r["title"]) > 150:
            problems.append(f"{who}: title is {len(r['title'])} chars (aim for 150 or fewer)")
        if len(r["description"]) > 5000:
            problems.append(f"{who}: description over 5,000 chars")
        if not re.fullmatch(r"\d+(\.\d{2})? [A-Z]{3}", r["price"]):
            problems.append(f"{who}: price {r['price']!r} is not 'number space CURRENCY'")
        if r["availability"] not in AVAILABILITY:
            problems.append(f"{who}: availability {r['availability']!r} not allowed")
        for col in ("url", "image_url", "seller_url", "seller_tos", "seller_privacy_policy"):
            if r.get(col) and not r[col].startswith("https://"):
                problems.append(f"{who}: {col} is not an https link")
        if not r["image_url"].lower().endswith((".png", ".jpg", ".jpeg")):
            problems.append(f"{who}: image_url must be a direct JPEG or PNG")
        for col, val in r.items():
            if (val or "").strip().lower() in {"n/a", "na", "none", "tbd", "null"}:
                problems.append(f"{who}: placeholder {val!r} in {col}")
    return problems


def write_images() -> None:
    from PIL import Image, ImageDraw, ImageFont  # imported lazily so --check needs no Pillow

    def font(size: int, bold: bool = False):
        for path in ("/System/Library/Fonts/Helvetica.ttc",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(path, size, index=1 if (bold and path.endswith(".ttc")) else 0)
            except OSError:
                continue
        return ImageFont.load_default()

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    for p in PRODUCTS:
        img = Image.new("RGB", (1200, 1200), "#0b0f0c")
        d = ImageDraw.Draw(img)
        d.rectangle([80, 80, 1120, 1120], outline="#c8f560", width=6)
        d.text((140, 150), "TRENDI", font=font(64, True), fill="#c8f560")
        d.text((140, 430), p["headline"], font=font(120, True), fill="#ffffff")
        d.text((140, 600), p["sub"], font=font(58), fill="#cfd8c8")
        d.text((140, 960), p["price_label"], font=font(76, True), fill="#c8f560")
        img.save(IMG_DIR / f"{p['item_id']}.png", "PNG", optimize=True)


def main() -> int:
    rows = [row(p) for p in PRODUCTS]
    problems = validate(rows)
    if "--check" in sys.argv:
        existing = list(csv.DictReader(CSV_PATH.open(encoding="utf-8", newline="")))
        problems += [f"existing CSV: {p}" for p in validate(existing)]
        print("\n".join(problems) or f"OK: {len(existing)} rows valid in {CSV_PATH}")
        return 1 if problems else 0
    if problems:
        print("\n".join(problems))
        return 1
    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    write_images()
    print(f"wrote {CSV_PATH} ({len(rows)} rows) and {len(rows)} images in {IMG_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
