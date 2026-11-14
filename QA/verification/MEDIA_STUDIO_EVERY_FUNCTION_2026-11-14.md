# Every media function, tested against the live service

"Nothing is generating" — so each of the four poster templates, the AI image and the video was
generated for real and the **bytes** were inspected, not just the status codes.

## Result: all six generate, and four defects were found doing it

| Function | Result |
| --- | --- |
| `POST /owner/media/image` · showcase | 201, PNG 1080×1080 |
| `POST /owner/media/image` · before_after | 201, PNG 1080×1080, photo in the BEFORE panel |
| `POST /owner/media/image` · quote | 201, PNG 1080×1080 (text-only by design) |
| `POST /owner/media/image` · service | 201, PNG 1080×1080 (text-only by design) |
| `POST /owner/media/ai-image` | 201, JPEG 1024×1024, real image (625 KB) |
| `POST /owner/media/video` | 201, MP4, 3.0 s, 141 KB — ffmpeg path works |
| `GET /owner/media/assets/{id}/file` | 200, correct content type, correct magic bytes |

## 1. A poster with no photo was a black rectangle

**Cause.** `showcase()` in `services/media-render/server.js` drew the photo if there was one and
otherwise left `#111111` behind a headline pinned to the bottom. Technically a valid PNG;
visually "nothing generated" — exactly how it was reported.

**Fix.** With no photo the canvas is now a colour field built from the business's accent colour
(two radial gradients over `#141518`), and the type is centred, larger and letter-spaced.

**Proof.** `QA/verification/media-branded-no-photo-2026-11-14.png` — the same request that
previously produced an empty black square. Guard:
`test_a_branded_poster_without_a_photo_is_still_designed`, which requires the field to be
**drawn** ("\n    fallback,\n" in the returned tree), not merely computed. Mutating the node out
while leaving the gradient string behind makes it fail, which is what the first, weaker version
of the check missed.

## 2. You could not see what you had made

**Cause.** "Your media" listed a kind, a timestamp and an *Open* button that opened a `blob:`
URL in a new tab. Nothing on the page ever showed the picture, so a successfully generated poster
was indistinguishable from a failure.

**Fix.** Each card renders the real bytes: `AssetPreview` fetches with the bearer token and shows
`<img>` or `<video>` (`c-thumb`, 1:1, cover). Verified in Chrome: 14 thumbnails, 11 images
decoded with `naturalWidth > 0`.

## 3. The success message claimed work that may not have happened

**Cause.** `to-social` was fire-and-forget and the status always said "Ready — added to your
social composer."

**Fix.** The follow-up call is awaited; the message is now *"Image made — it is in Your media
below."* plus either *"Also added to your social composer."* or *"Not added to the composer —
open Social to pick it up."* Verified live: "Image made — it is in Your media below. Also added to
your social composer." and "Video made — …".

## 4. Three of four templates were unreachable, and before/after shipped a blank half

**Cause.** `const [template] = useState('showcase')` — hard-coded; no selector was ever built.

**Fix.** A template picker (all four), and before/after now requires two photos: an explicit
message and a disabled button until then. (Verified by the guard; the first attempt at this edit
silently did not apply and the new guard caught it — which is why the guard exists.)

## Notes

* Cloudflare's bot protection answers the bare `python-urllib` user agent with `error code: 1010`
  — that was my test client, not the product. The same requests through `curl`, and through the
  browser, return 201.
* Video needs at least one photo; with none the server correctly answers 400 "At least one photo
  is required", and the UI now says so before you press it.
* Guards: `tests/test_studio_shell.py` now 18; suite **1171**.
