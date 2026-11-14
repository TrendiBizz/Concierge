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

## 5. "Added to your social composer" had nothing to pick it with

**Cause.** `to-social` copied the asset into the social service's library, but the composer had no
way to see or choose it — its only media path was a direct file upload. The promise in the page
copy was therefore half true.

**Fix.** The composer now lists your generated media as thumbnails ("Or use something you made in
Marketing media"); clicking one uploads it and adds the reference to the post being written.

**Proof.** Live Chrome run, in order: image generated → video generated (played: duration 3 s,
1080×1350, `playing: true`, reaching 0.78 s) → Social page offered **8** pickable assets →
clicked one → "Attached: 1". Screenshot `media-composer-picker-2026-11-14.png`.

**Defect inside that fix, also fixed and guarded.** The first build of the picker shipped an
empty list: the fetch ran and returned 200, but the result was dropped, because removing an unused
setter to satisfy TypeScript left nothing to store it. The guard now requires `setLibrary(` to be
called, not merely present; mutating the call out turns
`test_generated_media_can_be_used_in_a_post` red.

## Will it work when you press the button? Yes

Verified end to end against production on 2026-11-14 18:35–18:45 NZDT:

* branded image with a photo → "Image made — it is in Your media below. Also added to your social composer."
* video with a photo → "Video made — …", thumbnail present, **playback confirmed**
* AI image → real 1024×1024 JPEG
* every asset card shows a decoded thumbnail; "Open full size" opens the actual image
* the picker attaches to a post ("Attached: 1")

## 6. Deleting pictures, and "everything says Working…"

**Delete.** The API had `DELETE /owner/media/assets/{id}` from the start; the page never exposed
it, so in practice pictures were permanent. Every card now has **Delete**, which asks "Delete this
AI image? This cannot be undone.", deletes the row and the file, refreshes the list and the usage
meters, and reports "Deleted. Your storage and monthly count both went down."

Proof: 21 assets → 20 (also 21 → 20 on a second run), confirm dialog captured verbatim, status
message shown, no page errors. Guard: `test_media_can_be_deleted_from_the_page`.

**"All the other tabs show working."** One `const [busy, setBusy] = useState(false)` drove all
three generators, so pressing Generate AI image relabelled Generate image and Generate video to
"Working…" too. The flag is now the action itself (`'' | 'image' | 'video' | 'ai' | 'delete'`), each
button keys off its own value, and the others are simply disabled while one runs.

Proof: with the AI running, the only busy label on the page is "Making the AI image…"; the other
two still read "Generate image" and "Generate video". Guard:
`test_only_the_button_you_pressed_says_it_is_working` (mutating the shared flag back turns it red).

Note for the record: two of the three button edits silently did nothing on the first attempt —
the source had drifted under an earlier edit, and a string replace that finds nothing still
"passes". The guard is what caught it, and the fix was applied line by line with a check after.

## 7. A video works on its own, and deleting many at once

### 7a. "This doesn't work on its own — why do we need a picture or music?"

Both were **our** invention, and the photo one was enforced in two places:

* `VideoRequest.photos` was declared `min_length=1`, so a headline-only request came back
  `{"detail": "Photos is not valid."}` — a 422 telling the customer their own input was wrong.
* The renderer threw `At least one photo is required`, and the page disabled the button.

Now: photos and music are both genuinely optional. With no photo the renderer draws a **title
card** with the showcase template (brand, headline, accent rule) and animates it with a slow
`zoompan`, so pressing Generate on a headline alone yields a 6-second, 1080×1350 video.

Proof:
* `POST /owner/media/video` with `{"format":"portrait","headline":"…"}` and no photos → **201**,
  MP4, duration **6.00 s**, 386 KB. Frame extracted at 3 s:
  `media-video-no-photo-2026-11-14.png`.
* In the browser with nothing but a headline: status "Video made — it is in Your media below.",
  network `201 media/video`, and the new thumbnail **plays** (duration 6 s, 1080×1350).
* Headline *and* photo still produce the original slideshow with the headline overlaid.

Guards: `test_video_needs_neither_a_photo_nor_music` (mutating the field back to `min_length=1`
turns it red — verified by mutating the actual field line) and
`test_the_renderer_draws_a_title_card_when_there_is_no_photo`.

### 7b. Deleting one at a time

Clearing a dozen test images meant a dozen confirmations. Each card now has a tick box, there is
a **Select all**, a live "N of M selected" count, and **Delete selected (n)** with one
confirmation. Backed by a new `POST /owner/media/assets/delete` that removes the rows and files in
one call and returns how many went.

Proof (live): three ticked → "3 of 20 selected" → confirm "Delete 3 items? This cannot be undone."
→ cards **20 → 17** → "Deleted 3. Your storage and monthly counts went down."
Screenshot `media-bulk-delete-2026-11-14.png`.

## 8. What "AI video" honestly is, and what a real video model needs

### 8a. The defect: four unrelated stills sold as a video

Asked for "a flower slowly opening and swaying in a breeze", the first build generated **four
unrelated photographs** of a flower and moved the camera over each of them. Nothing opened,
nothing swayed, and the UI said "Generate AI video". That is our failure of both implementation
and honesty.

**Fixed** (as far as this stack allows): the clip now draws **two states of the same scene** — the
comment *"The very start of this action, about to happen"* and *"The end of this action, a moment
later, the action complete"* — and dissolves between them while the frame sways on a slow sine.
The subject visibly changes across the clip.

Proof: start frame (`m_0.3`) shows a mostly-closed flower on its stem; end frame (`m_5.2`) shows it
fully open and larger. Clip is 10.2 s, 1080×1350, generated through the page in ~21 s
("AI clip made"). Guards: `test_the_ai_clip_shows_the_scene_changing_not_four_unrelated_stills`
(mutating the end-state phrasing away turns it red) and
`test_the_ai_clip_does_not_claim_to_be_generated_video`.

**Copy corrected.** The button is "Generate AI clip", and the card says plainly: *"AI draws the
first and last moment of that scene and dissolves between them, with a gentle sway. True
frame-by-frame motion needs a video model, which we do not have yet."*

### 8b. Why there is no true text-to-video: evidence, not an opinion

Probed on the production host, 2026-11-14:

| Model id | Result |
| --- | --- |
| `@cf/lightricks/ltx-video` | 400 `{"code":7000,"message":"No route for that URI"}` |
| `@cf/luma/luma-video` | 400 same |
| `@cf/runway/gen3` | 400 same |
| `@cf/black-forest-labs/flux-1-schnell` | **200**, image returned |

The account's catalogue (`/ai/models/search`): 75 models — 10 Text-to-Image, 40 Text Generation,
4 Text-to-Speech, **0 video tasks**. No `RUNWAY/LUMA/PIKA/REPLICATE/FAL/OPENAI/GOOGLE/VEO` keys
exist in `compose.env` or `api.env`.

Host: **2 cores, 7 GB RAM, no GPU** (`nvidia-smi` absent). Local open-weight video models need a
CUDA GPU with 8–24 GB VRAM, so they cannot run here.

### 8c. Open item — true text-to-video (blocked on credentials or a GPU)

Open-weight options on GitHub, with what they need:

| Project | License | Minimum VRAM | Notes |
| --- | --- | --- | --- |
| **Wan 2.2 / 2.1** (Alibaba) | Apache-2.0 | 24 GB (5B, with offload); 1.3B variant fits ~8 GB | Best all-round; T2V and I2V |
| **LTX-Video** (Lightricks) | LTX Open Weights License | 2B distilled runs on 8–12 GB | Built for speed; closest to "click and get a clip" |
| **CogVideoX 1.5** (Zhipu) | CogVideoX License | 10 GB BF16 / 7 GB INT8 | 1360×768, 5 or 10 s |
| **HunyuanVideo 1.5** (Tencent) | Tencent Community License | 14 GB with offload | Strong quality; licence terms need review |
| **Mochi 1** (Genmo) | Apache-2.0 | 22 GB low-precision | 480p; permissive, hackable |

Path chosen by the operator decides the work: a hosted API key (fal/Replicate host Wan and LTX)
is wired into `/owner/media/ai-video` behind the existing renderer seam in roughly an hour and
needs no hardware; self-hosting needs a rented GPU box and a second deployment. **No code change
is possible until one of those exists** — this is recorded in the handoff Outstanding list with
the next action.
