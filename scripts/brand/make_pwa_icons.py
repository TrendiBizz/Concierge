"""Generate the Concierge home-screen icons.

Why this exists: the shipped icons were a lime tile with a near-black "C". On a phone in dark mode
the system can render a home-screen web app icon with a dark treatment, and a dark glyph on a bright
tile collapsed into an unreadable blob (reported 2026-11-16). The icon is now a dark tile with a
thick lime "C": high contrast in light and dark, and a silhouette that survives being tinted.

Every icon is fully opaque. An apple-touch-icon with transparency is composited onto black by iOS,
which is the other way a logo becomes a blob.

Usage: python3 scripts/brand/make_pwa_icons.py
"""
from __future__ import annotations

import pathlib
import sys

from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parents[2] / "web" / "portal" / "public"
INK = (16, 16, 20, 255)        # #101014 tile
LIME = (200, 245, 96, 255)     # #c8f560 glyph
SCALE = 4                      # draw big, downsample for clean edges


def draw_c(size: int, margin: float) -> Image.Image:
    """A thick, geometric C — no font dependency, and a strong silhouette when tinted."""
    canvas = size * SCALE
    image = Image.new("RGB", (canvas, canvas), INK[:3])
    draw = ImageDraw.Draw(image)
    pad = int(canvas * margin)
    stroke = int((canvas - 2 * pad) * 0.17)
    box = (pad, pad, canvas - pad, canvas - pad)
    # Ring, then cut the right-hand gap so it reads as a C rather than an O.
    draw.ellipse(box, outline=LIME[:3], width=stroke)
    gap = int(canvas * 0.30)
    draw.rectangle((canvas // 2 + gap // 2, canvas // 2 - stroke, canvas, canvas // 2 + stroke),
                   fill=INK[:3])
    return image.resize((size, size), Image.LANCZOS)


def save(image: Image.Image, name: str) -> None:
    path = OUT / name
    # No alpha: iOS composites transparent pixels onto black.
    image.convert("RGB").save(path, "PNG", optimize=True)
    print(f"{name}: {image.size[0]}x{image.size[1]}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    save(draw_c(192, 0.20), "icon-192.png")
    save(draw_c(512, 0.20), "icon-512.png")
    # Maskable: the safe zone is the inner 80%, so keep more space around the mark.
    save(draw_c(512, 0.26), "icon-maskable-512.png")
    save(draw_c(180, 0.20), "apple-touch-icon.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
