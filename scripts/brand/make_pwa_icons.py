"""Generate the Concierge / Studio home-screen icons from the Trendi refresh mark.

The mark is website/brand/mark-refresh.svg: a purple #7142d6 rounded square (rx 15 of 48) with a white
up-right arrow (path "M14 34l20-20m-16 0h16v16", stroke 4, round caps and joins). This script draws
that same geometry with Pillow (no SVG renderer needed), so the icons match website/brand/icon-512.png
and apple-touch-icon.png. It replaced the retired lime "C" icons.

Every icon is fully opaque (RGB). An apple-touch-icon with transparency is composited onto black by
iOS, which is how a logo becomes a blob. Corners of the rounded "any" icons are white, like the site's
own icons; the maskable icon is a full-bleed purple square with the arrow inside the 80% safe zone.

Usage: python3 scripts/brand/make_pwa_icons.py  (needs Pillow)
Also writes web/portal/public/favicon.svg and api/static/favicon.svg from mark-refresh.svg.
"""
from __future__ import annotations

import pathlib
import shutil
import sys

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "portal" / "public"
MARK_SVG = ROOT / "website" / "brand" / "mark-refresh.svg"
PURPLE = (0x71, 0x42, 0xD6)
WHITE = (255, 255, 255)
SCALE = 4  # draw big, downsample for clean edges

# Arrow geometry in the 48x48 viewBox of mark-refresh.svg.
SEGMENTS = [((14, 34), (34, 14)), ((18, 14), (34, 14)), ((34, 14), (34, 30))]
STROKE = 4


def draw_mark(size: int, rounded: bool = True, arrow_scale: float = 1.0) -> Image.Image:
    """Opaque RGB mark. arrow_scale<1 shrinks the arrow about the centre (maskable safe zone)."""
    canvas = size * SCALE
    u = canvas / 48
    image = Image.new("RGB", (canvas, canvas), WHITE)
    draw = ImageDraw.Draw(image)
    if rounded:
        draw.rounded_rectangle((0, 0, canvas - 1, canvas - 1), radius=15 * u, fill=PURPLE)
    else:
        draw.rectangle((0, 0, canvas, canvas), fill=PURPLE)

    def pt(p):
        return (24 + (p[0] - 24) * arrow_scale) * u, (24 + (p[1] - 24) * arrow_scale) * u

    width = STROKE * arrow_scale * u
    for a, b in SEGMENTS:
        pa, pb = pt(a), pt(b)
        draw.line([pa, pb], fill=WHITE, width=round(width))
        for cx, cy in (pa, pb):  # round caps and joins
            r = width / 2
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WHITE)
    return image.resize((size, size), Image.LANCZOS)


def save(image: Image.Image, name: str) -> None:
    path = OUT / name
    image.convert("RGB").save(path, "PNG", optimize=True)  # no alpha
    print(f"{name}: {image.size[0]}x{image.size[1]}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    save(draw_mark(192), "icon-192.png")
    save(draw_mark(512), "icon-512.png")
    # Maskable: the safe zone is the inner 80%, so a full-bleed tile and a smaller arrow.
    save(draw_mark(512, rounded=False, arrow_scale=0.8), "icon-maskable-512.png")
    save(draw_mark(180), "apple-touch-icon.png")
    for dest in (OUT / "favicon.svg", ROOT / "api" / "static" / "favicon.svg"):
        shutil.copyfile(MARK_SVG, dest)
        print(f"{dest.relative_to(ROOT)}: copied from mark-refresh.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
