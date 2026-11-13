# QR code for the hosted chat link — 2026-11-13

Hosted chat is the fallback for a customer who cannot edit their own site, and they usually want
to try it on a phone. Reading a long URL off a laptop screen is exactly the friction we are
removing, so the hosted link now shows a QR code, and the code can be downloaded to print.

## How it is made

- Library: `qrcode-generator@2.0.4` (zero dependencies, ships its own TypeScript types).
- **Rendered in the browser**, not by an external QR service. Nothing about the customer's link
  leaves the page, there is no third-party request and no image to host.
- Drawn as **SVG**, so it stays crisp at any size and on a printed leaflet. `Download the QR to
  print` saves the same code at a larger cell size.
- If generation ever throws, the component renders nothing rather than a broken square: the link
  and the copy button still work.

## Why it is tested rather than assumed

A QR that renders but scans to the wrong text is worse than no QR at all, and a screenshot cannot
prove one decodes. So the matrix is emitted from the same library the browser uses, turned into a
image, and **decoded by an independent reader**.

Reproduce (from `web/portal/`):

```bash
# 1. Emit the matrix exactly as the component generates it
cat > qr_emit.mjs <<'JS'
import qrcode from 'qrcode-generator';
const url = process.argv[2];
const code = qrcode(0, 'M');
code.addData(url); code.make();
const n = code.getModuleCount(); const rows = [];
for (let r = 0; r < n; r++) { let row = '';
  for (let c = 0; c < n; c++) row += code.isDark(r, c) ? '1' : '0';
  rows.push(row); }
console.log(JSON.stringify({url, n, rows}));
JS
node qr_emit.mjs "https://chat.trendibizz.com/demo/pukeko-construction" > /tmp/qr.json
rm qr_emit.mjs
```

```python
# 2. Draw it with a quiet zone, exactly as a scanner will see it
import json
from PIL import Image
d = json.load(open('/tmp/qr.json')); n, scale, quiet = d['n'], 8, 4
size = (n + quiet * 2) * scale
img = Image.new('1', (size, size), 1); px = img.load()
for r, row in enumerate(d['rows']):
    for c, ch in enumerate(row):
        if ch == '1':
            for y in range((r + quiet) * scale, (r + quiet + 1) * scale):
                for x in range((c + quiet) * scale, (c + quiet + 1) * scale):
                    px[x, y] = 0
img.save('/tmp/qrcheck/qr.png')
```

```bash
# 3. Decode with an independent reader
docker run --rm -v /tmp/qrcheck:/w python:3.12-slim sh -c "pip install -q opencv-python-headless && python -c \"
import cv2; img = cv2.imread('/w/qr.png')
text, _, _ = cv2.QRCodeDetector().detectAndDecode(img); print(repr(text))\"" 
```

## Result

```
modules : 33 x 33        (version 3, error correction M)
decoded : 'https://chat.trendibizz.com/demo/pukeko-construction'
expected: 'https://chat.trendibizz.com/demo/pukeko-construction'
MATCH
```

## Deployed

Portal bundle `assets/index-As248SKq.js` served from `/studio/`: contains the QR label, the print
download and the capability cards; `/studio/` returns 200. API unchanged by this work.

**Not yet seen on a real phone.** The decode above proves the code carries the right text; only a
camera confirms the on-screen size is comfortable to scan, which is the next thing to check during
the setup walkthrough.
