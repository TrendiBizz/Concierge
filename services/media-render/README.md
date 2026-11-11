# Concierge media renderer

Internal sidecar for client marketing media. No GPU, no local model weights.

- `POST /render/image` — Satori template → PNG (showcase, before_after, quote, service)
- `POST /render/video` — FFmpeg photo slideshow → MP4 (silent, headline overlay)
- `POST /ai-image` — Cloudflare Workers AI `flux-1-schnell` → JPEG
- `GET /health`

Env: `CF_ACCOUNT_ID`, `CF_API_KEY`, `CF_EMAIL` (AI images), `PORT` (8099).
Fonts: DejaVu from `ttf-dejavu` (Alpine).

Build: `docker compose build media-render` from `scripts/vps/`.
The API reaches it at `http://media-render:8099`; it is not published to the host.
