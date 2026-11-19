"""Generate every raster icon from the one Trendi mark (website/brand/mark-refresh.svg).

The mark is a purple (#7142d6) rounded tile with a white up-right arrow. It is the same mark
the website header uses (website/brand/logo-refresh.svg), so the public site, the owner workspace,
the Studio app, the browser tab and the phone home screen all show one logo in one colour.

Rules kept from the earlier icon incident (2026-11-16): apple-touch and maskable icons are fully
opaque (iOS composites transparency onto black), and the glyph is thick so it survives tinting.

Usage: python3 scripts/brand/make_pwa_icons.py
"""
from __future__ import annotations

import pathlib
import sys

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[2]
STUDIO = ROOT / "web" / "portal" / "public"
SITE = ROOT / "website" / "brand"
PURPLE = (113, 66, 214)  # #7142d6
WHITE = (255, 255, 255)
SCALE = 4  # draw big, downsample for clean edges


def mark(size: int, *, rounded: bool, inset: float = 0.0) -> Image.Image:
    """The Trendi mark. `inset` shrinks the arrow toward the centre (maskable safe zone)."""
    canvas = size * SCALE
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0) if rounded else PURPLE + (255,))
    draw = ImageDraw.Draw(image)
    if rounded:
        draw.rounded_rectangle((0, 0, canvas - 1, canvas - 1), radius=int(canvas * 15 / 48), fill=PURPLE + (255,))
    unit = canvas / 48.0
    centre = 24.0

    def p(x: float, y: float) -> tuple[float, float]:
        return ((centre + (x - centre) * (1 - inset)) * unit, (centre + (y - centre) * (1 - inset)) * unit)

    width = int(4 * unit * (1 - inset))
    for a, b in (((14, 34), (34, 14)), ((18, 14), (34, 14)), ((34, 14), (34, 30))):
        draw.line([p(*a), p(*b)], fill=WHITE, width=width)
    for pt in ((14, 34), (34, 14), (18, 14), (34, 30)):  # round caps and joins
        x, y = p(*pt)
        r = width / 2
        draw.ellipse((x - r, y - r, x + r, y + r), fill=WHITE)
    return image.resize((size, size), Image.LANCZOS)


def save(image: Image.Image, path: pathlib.Path, *, opaque: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = image.convert("RGB") if opaque else image
    out.save(path, "PNG", optimize=True)
    print(f"{path.relative_to(ROOT)}: {image.size[0]}x{image.size[1]}")


def main() -> int:
    # Studio (installed web app)
    save(mark(192, rounded=False, inset=0.10), STUDIO / "icon-192.png", opaque=True)
    save(mark(512, rounded=False, inset=0.10), STUDIO / "icon-512.png", opaque=True)
    save(mark(512, rounded=False, inset=0.22), STUDIO / "icon-maskable-512.png", opaque=True)
    save(mark(180, rounded=False, inset=0.10), STUDIO / "apple-touch-icon.png", opaque=True)
    # Public website
    save(mark(512, rounded=True), SITE / "icon-512.png", opaque=False)
    save(mark(180, rounded=False, inset=0.10), SITE / "apple-touch-icon.png", opaque=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
