#!/usr/bin/env python3
"""Inject the public-site language switcher into every static page."""
from pathlib import Path
import sys

site = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/trendi/releases/20261108-vps/website/site")
for page in site.glob("*.html"):
    text = page.read_text()
    if "site-i18n.js" in text:
        continue
    text = text.replace("</head>", '<link rel="stylesheet" href="/site-i18n.css">\n</head>', 1)
    text = text.replace("</body>", '<script src="/site-i18n.js" defer></script>\n</body>', 1)
    page.write_text(text)
print("injected")
