"""Generate the Concierge icons from the Concierge bell tile (Jo, 2026-11-23: the only Concierge logo).

Source (not redrawn): scripts/brand/concierge-icon/icon-tile-1024.png (+ icon-tile.svg, favicon.svg), copied from
~/jo-jobs/concierge-icon-swap/concierge-logo/concierge-logo-1a/. The old purple arrow script is retired.

Writes: web/portal/public/{icon-192,icon-512,icon-maskable-512,apple-touch-icon}.png and favicon.svg,
api/static/favicon.svg, website/brand/{favicon.svg,apple-touch-icon.png,icon-512.png}, website/favicon.ico,
crm/web/favicon.svg, workflows/web/favicon.svg, calendars/web/favicon.svg, payments/web/favicon.svg,
sites/web/favicon.svg, concierge-stack/platform-website/favicon.svg.
Every PNG is opaque RGB: "any" icons get white corners (as before), the apple-touch-icon and the maskable icon
are full-bleed purple (iOS rounds the corners itself; transparency becomes black). Maskable: tile at 80%.

Usage: python3 scripts/brand/make_pwa_icons.py  (needs Pillow)
"""
from __future__ import annotations

import pathlib
import shutil
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "scripts" / "brand" / "concierge-icon"
PORTAL = ROOT / "web" / "portal" / "public"
PURPLE = (0x71, 0x42, 0xD6, 255)
WHITE = (255, 255, 255, 255)


def flat(tile: Image.Image, bg, size: int) -> Image.Image:
    canvas = Image.new("RGBA", tile.size, bg)
    canvas.alpha_composite(tile)
    return canvas.convert("RGB").resize((size, size), Image.LANCZOS)


def save(image: Image.Image, path: pathlib.Path) -> None:
    image.save(path, "PNG", optimize=True)
    print(f"{path.relative_to(ROOT)}: {image.size[0]}x{image.size[1]}")


def main() -> int:
    tile = Image.open(SRC / "icon-tile-1024.png").convert("RGBA")
    save(flat(tile, WHITE, 192), PORTAL / "icon-192.png")
    save(flat(tile, WHITE, 512), PORTAL / "icon-512.png")
    maskable = Image.new("RGB", (1024, 1024), PURPLE[:3])
    maskable.paste(flat(tile, PURPLE, 819), (102, 102))
    save(maskable.resize((512, 512), Image.LANCZOS), PORTAL / "icon-maskable-512.png")
    touch = flat(tile, PURPLE, 180)
    save(touch, PORTAL / "apple-touch-icon.png")
    save(touch, ROOT / "website" / "brand" / "apple-touch-icon.png")
    save(tile.resize((512, 512), Image.LANCZOS), ROOT / "website" / "brand" / "icon-512.png")
    ico = [tile.resize((s, s), Image.LANCZOS) for s in (48, 32, 16)]
    ico[0].save(ROOT / "website" / "favicon.ico", format="ICO", sizes=[(48, 48), (32, 32), (16, 16)], append_images=ico[1:])
    for dest in (
        PORTAL / "favicon.svg",
        ROOT / "api" / "static" / "favicon.svg",
        ROOT / "website" / "brand" / "favicon.svg",
        ROOT / "crm" / "web" / "favicon.svg",
        ROOT / "workflows" / "web" / "favicon.svg",
        ROOT / "calendars" / "web" / "favicon.svg",
        ROOT / "payments" / "web" / "favicon.svg",
        ROOT / "sites" / "web" / "favicon.svg",
        ROOT / "concierge-stack" / "platform-website" / "favicon.svg",
    ):
        shutil.copyfile(SRC / "favicon.svg", dest)
        print(f"{dest.relative_to(ROOT)}: copied from concierge-icon/favicon.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
