"""Public, widget, chat, hosted demo/report, Studio PWA shell, static assets, and website
enquiry routes.

Moved out of app/main.py unchanged; paths and behaviour are identical. main.py re-exports the
handlers, helpers, and request models so existing imports (tests, tooling) keep working.
"""
import base64
import html
import json
import logging
import re
import sys
import time
from typing import Literal
from urllib.parse import quote_plus

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import RedirectResponse

from .. import (
    a2ui, channel_authorization, chat as chat_engine, cloudflare_auth, convo, db, llm,
    robots_fetch, site_enquiry, site_tools, tenants,
)
from ..security import html_with_script_nonce

log = logging.getLogger("concierge")
router = APIRouter()


def _main():
    return sys.modules[__package__.rsplit(".", 1)[0] + ".main"]


# ------------------------------------------------------------- public API
@router.get("/healthz")
async def healthz():
    await db.pool().fetchval("SELECT 1")
    return {"ok": True}


@router.get("/status")
@router.get("/owner/status")
async def service_status():
    """Point-in-time readiness, never a claim about historical uptime."""
    from datetime import datetime, timezone
    from fastapi.responses import JSONResponse
    try:
        import asyncio
        await asyncio.wait_for(db.pool().fetchval("SELECT 1"), timeout=3)
        healthy = True
    except Exception:
        healthy = False
    return JSONResponse({
        "status": "operational" if healthy else "degraded",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "components": {"api": "operational", "database": "operational" if healthy else "degraded"},
        "scope": "Current API and database readiness; voice, email and carrier delivery are not independently probed.",
    }, status_code=200 if healthy else 503, headers={"Cache-Control": "no-store"})


@router.get("/widget.js")
async def widget_js():
    return FileResponse(
        _main().STATIC_DIR / "widget.js",
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/a2ui-renderer.js")
async def a2ui_renderer_js():
    return FileResponse(_main().STATIC_DIR / "a2ui-renderer.js", media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=300"})


class PublicTranslateRequest(BaseModel):
    locale: str = Field(min_length=2, max_length=12)
    strings: list[str] = Field(min_length=1, max_length=80)


_GOOGLE_LOCALE = {"pt-BR": "pt", "pt-PT": "pt", "zh-CN": "zh-CN", "zh-TW": "zh-TW"}


async def _google_translate(values: list[str], locale: str) -> dict[str, str]:
    code = _GOOGLE_LOCALE.get(locale, locale.split("-")[0])
    joined = "\n".join(values)
    url = "https://translate.googleapis.com/translate_a/single"
    params = {"client": "gtx", "sl": "en", "tl": code, "dt": "t", "q": joined}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    translated = "".join(segment[0] for segment in data[0] if segment and segment[0])
    parts = translated.split("\n")
    if len(parts) == len(values):
        return dict(zip(values, parts))
    return {value: (parts[index] if index < len(parts) else value) for index, value in enumerate(values)}


_translate_hits: dict[str, list[float]] = {}


@router.post("/api/v1/translate")
async def public_translate(body: PublicTranslateRequest, request: Request):
    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin and origin not in {"https://trendibizz.com", "https://www.trendibizz.com"}:
        raise HTTPException(403, "Origin not allowed")
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    hits = [stamp for stamp in _translate_hits.get(ip, []) if now - stamp < 60]
    if len(hits) >= 30:
        raise HTTPException(429, "Too many translation requests")
    _translate_hits[ip] = hits + [now]
    locale = body.locale.strip()
    if locale == "en":
        return {"locale": locale, "strings": {source: source for source in body.strings}}
    requested = []
    for source in body.strings:
        value = source.strip()
        if value and len(value) <= 300 and value not in requested:
            requested.append(value)
    if not requested:
        return {"locale": locale, "strings": {}}
    rows = await db.pool().fetch(
        "SELECT source, translated FROM ui_translation_cache WHERE locale=$1 AND source=ANY($2::text[])",
        locale, requested)
    found = {row["source"]: row["translated"] for row in rows}
    missing = [value for value in requested if value not in found]
    if missing:
        settings = _main().get_settings()
        if settings.cloudflare_account_id and cloudflare_auth.configured(settings):
            try:
                prompt = ("Translate these website strings into locale " + locale + ". "
                          "Keep brand names Trendi and Concierge. Return only a JSON object "
                          "with the same keys and translated values. " +
                          json.dumps({value: value for value in missing}, ensure_ascii=False))
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(
                        f"https://api.cloudflare.com/client/v4/accounts/{settings.cloudflare_account_id}/ai/run/@cf/meta/llama-3.1-8b-instruct",
                        headers={**cloudflare_auth.headers(settings), "Content-Type": "application/json"},
                        json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 4096})
                data = response.json()
                result = data.get("result") or {}
                content = (result.get("response")
                           or ((result.get("choices") or [{}])[0].get("message") or {}).get("content")
                           or "")
                content = str(content).strip()
                if not content:
                    log.warning("translation model response: %s", str(data)[:400])
                    raise RuntimeError("empty translation response")
                content = content[content.find("{"):content.rfind("}") + 1]
                translated = json.loads(content)
                if len(translated) == 1 and isinstance(next(iter(translated.values())), dict):
                    translated = next(iter(translated.values()))
                for source in missing:
                    value = str(translated.get(source, source))
                    if not value or value == source:
                        continue
                    found[source] = value
                    await db.pool().execute(
                        "INSERT INTO ui_translation_cache(locale,source,translated) VALUES($1,$2,$3) "
                        "ON CONFLICT (locale,source) DO NOTHING", locale, source, value)
            except Exception:
                log.exception("public translation failed")
        still = [value for value in missing if value not in found]
        if still:
            try:
                found.update(await _google_translate(still, locale))
                for source in still:
                    value = found.get(source, source)
                    if not value or value == source:
                        continue
                    await db.pool().execute(
                        "INSERT INTO ui_translation_cache(locale,source,translated) VALUES($1,$2,$3) "
                        "ON CONFLICT (locale,source) DO NOTHING", locale, source, value)
            except Exception:
                log.exception("google translation fallback failed")
        for source in missing:
            found.setdefault(source, source)
    return {"locale": locale, "strings": {source: found[source] for source in requested}}


@router.get("/api/v1/widget-logo")
async def widget_logo(request: Request, key: str):
    from .. import media_studio
    tenant = await _main()._tenant_for(request, key)
    row = await db.pool().fetchrow("SELECT logo_data FROM media_brand WHERE tenant_id=$1", tenant["id"])
    data = row["logo_data"] if row else None
    if not data:
        raise HTTPException(404, "Logo unavailable")
    try:
        mime, raw = media_studio.parse_logo_data_uri(data)
    except ValueError:
        raise HTTPException(404, "Logo unavailable") from None
    return Response(raw, media_type=mime,
                    headers={
                        "Cache-Control": "public, max-age=300",
                        "Content-Security-Policy": "default-src 'none'; sandbox",
                    })


@router.get("/api/v1/widget-config")
async def widget_config(request: Request, key: str):
    m = _main()
    tenant = await m._tenant_for(request, key)
    result = tenants.public_view(tenant)
    brand = await db.pool().fetchrow("SELECT logo_data FROM media_brand WHERE tenant_id=$1", tenant["id"])
    if brand and brand["logo_data"]:
        result["logo_url"] = "/api/v1/widget-logo?key=" + quote_plus(key)
    result["recording_available"] = bool(
        m.settings.voice_recording_enabled
        and tenant.get("voice_enabled")
        and await channel_authorization.is_authorized(tenant["id"], "call_recording")
    )
    return result


class ChatRequest(BaseModel):
    key: str
    session_id: str
    message: str = Field(min_length=1, max_length=1000)
    page_url: str | None = None
    utm: dict[str, str] = {}
    a2ui_version: Literal["0.8"] | None = None


@router.post("/api/v1/chat")
async def chat(req: ChatRequest, request: Request):
    m = _main()
    session_id = convo.clean_session(req.session_id)
    m._rate_limit(request, session_id)
    tenant = await m._tenant_for(request, req.key)
    try:
        result = await chat_engine.run_turn(
            tenant, session_id, "chat", req.message, page_url=req.page_url, utm=req.utm
        )
    except llm.LLMNotConfigured:
        raise HTTPException(status_code=503, detail="AI is not configured")
    except HTTPException:
        raise
    except Exception:
        log.exception("chat failed for tenant %s", tenant["slug"])
        raise HTTPException(status_code=502, detail="The assistant is temporarily unavailable")
    return {
        "a2ui": a2ui.card(kind) if req.a2ui_version and not result.get("suppressed") and (kind := a2ui.choose(req.message, tenant)) else [],
        "reply": result["reply"],
        "lead_captured": result["lead_captured"],
        "booking_url": result["booking_url"],
        "appointment": result["appointment"],
    }


@router.post("/api/v1/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """Server-sent token stream for the website widget (same turn semantics)."""
    m = _main()
    session_id = convo.clean_session(req.session_id)
    m._rate_limit(request, session_id)
    tenant = await m._tenant_for(request, req.key)

    async def events():
        try:
            async for event in chat_engine.run_turn_stream(
                tenant, session_id, "chat", req.message, page_url=req.page_url, utm=req.utm
            ):
                if event.get("type") == "done" and req.a2ui_version and not event.get("suppressed"):
                    kind = a2ui.choose(req.message, tenant)
                    if kind:
                        for message in a2ui.card(kind):
                            yield "data: " + json.dumps({"type": "a2ui", "message": message}) + "\n\n"
                yield "data: " + json.dumps(event, default=str) + "\n\n"
        except llm.LLMNotConfigured:
            yield 'data: {"type":"error","message":"AI is not configured"}\n\n'
        except Exception:
            log.exception("chat stream failed for tenant %s", tenant["slug"])
            yield 'data: {"type":"error"}\n\n'

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


class A2UIUserAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=40)
    surfaceId: str = Field(max_length=100)
    sourceComponentId: str = Field(max_length=40)
    timestamp: str = Field(min_length=20, max_length=40)
    context: dict[str, str] = Field(max_length=5)


class A2UIActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(max_length=200)
    session_id: str = Field(max_length=200)
    userAction: A2UIUserAction
    page_url: str | None = Field(default=None, max_length=2000)


@router.post("/api/v1/chat/action")
async def a2ui_action(req: A2UIActionRequest, request: Request):
    """Save a structured request through the existing enquiry pipeline. Never reserve or charge."""
    from .. import enquiries
    m = _main()
    session_id = convo.clean_session(req.session_id)
    m._rate_limit(request, session_id)
    tenant = await m._tenant_for(request, req.key)
    try:
        kind, values = a2ui.validate_action(req.userAction.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if kind == "pricing" and tenant.get("slug") not in a2ui.PRICING_TENANTS:
        raise HTTPException(403, "Plan unavailable")
    conversation_id = await convo.get_or_create(tenant, session_id, "chat", req.page_url, {})
    # Store as a visitor request, never execute text as instructions or log contact details.
    text = "Structured " + kind + " request: " + json.dumps(values, ensure_ascii=False)
    await convo.save_message(conversation_id, "user", text)
    if kind != "confirmation":
        await enquiries.capture(tenant, "chat", str(conversation_id) + ":" + req.userAction.surfaceId, text, conversation_id=conversation_id,
                                email=values.get("email", ""))
    reply = "Acknowledgement saved." if kind == "confirmation" else a2ui.TEXT["confirmation"]
    await convo.save_message(conversation_id, "assistant", reply)
    return {"reply": reply, "a2ui": [] if kind == "confirmation" else a2ui.card("confirmation")}


# -------------------------------------------------------------- demo page
@router.get("/demo/{slug}", response_class=HTMLResponse)
async def demo_page(slug: str, presenter: int = 0):
    tenant = await tenants.get_by_slug(slug)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown demo")

    excerpt = await db.pool().fetchval(
        "SELECT content FROM chunks WHERE tenant_id = $1 ORDER BY id LIMIT 1", tenant["id"]
    )
    name = html.escape(tenant["name"])
    excerpt_html = html.escape((excerpt or "")[:700]).replace("\n", "<br>")
    site = tenant.get("site_url") or ""
    site_html = html.escape(site) if site.startswith(("http://", "https://")) else ""

    questions = tenant["demo_questions"]
    if isinstance(questions, str):
        questions = json.loads(questions)
    panel = ""
    if presenter and questions:
        items = "".join(f"<li>{html.escape(q)}</li>" for q in questions)
        panel = f"<aside><h2>Questions to ask</h2><ol>{items}</ol></aside>"

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} - AI guide demo</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:0;color:#111;background:#fafafa}}
 header{{padding:24px;background:{html.escape(tenant['accent_color'])};color:#fff}}
 main{{max-width:760px;margin:32px auto;padding:0 16px;line-height:1.6}}
 aside{{position:fixed;left:16px;bottom:16px;max-width:380px;background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px 16px;font-size:14px}}
 small{{color:#666}}
</style></head>
<body>
<header><h1 style="margin:0">{name}</h1><small style="color:#fff;opacity:.85">Sandbox preview of your AI guide{' - ' + site_html if site_html else ''}</small></header>
<main><p>{excerpt_html}</p></main>
{panel}
<script src="/widget.js" data-key="{html.escape(tenant['public_key'])}" data-autoopen="1" defer></script>
</body></html>"""
    return HTMLResponse(page)


# ------------------------------------------------------------ client report
def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


@router.get("/report/{token}", response_class=HTMLResponse)
async def client_report(token: str, days: int = 30):
    """Read-only monthly report for the client. The unguessable token is the credential."""
    tenant = await tenants.get_by_report_token(token)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown report")
    s = await _main()._stats(tenant, days)

    peak = max([d["leads"] for d in s["daily"]] + [d["conversations"] for d in s["daily"]] + [1])
    bar_w = 600 / max(len(s["daily"]), 1)
    bars = []
    for i, d in enumerate(s["daily"]):
        x = i * bar_w
        h_c = 100 * d["conversations"] / peak
        h_l = 100 * d["leads"] / peak
        bars.append(
            f'<rect x="{x:.1f}" y="{110 - h_c:.1f}" width="{max(bar_w * 0.4, 1):.1f}" height="{h_c:.1f}" fill="#94a3b8"/>'
            f'<rect x="{x + bar_w * 0.45:.1f}" y="{110 - h_l:.1f}" width="{max(bar_w * 0.4, 1):.1f}" height="{h_l:.1f}" fill="{html.escape(tenant["accent_color"])}"/>'
        )
    leads = await db.pool().fetch(
        "SELECT name, message, channel, status, score_label, created_at FROM leads WHERE tenant_id = $1 "
        "AND created_at > now() - make_interval(days => $2) ORDER BY created_at DESC LIMIT 25",
        tenant["id"], s["days"],
    )
    rows = "".join(
        f"<tr><td>{r['created_at']:%b %d}</td><td>{html.escape((r['name'] or 'Visitor').split(' ')[0])}</td>"
        f"<td>{html.escape(r['message'][:140])}</td><td>{html.escape(r['channel'])}</td><td>{html.escape(r['status'])}</td>"
        f"<td>{html.escape((r['score_label'] or 'cold').title())}</td></tr>"
        for r in leads
    )
    card = lambda label, value: f'<div class="c"><b>{value}</b><span>{label}</span></div>'  # noqa: E731
    cards = "".join([
        card("Visitor conversations", s["conversations"]),
        card("Leads captured", s["leads"]),
        card("Appointments booked", s["appointments"]),
        card("Estimated pipeline", _money(s["estimated_pipeline_cents"]) if s["estimated_pipeline_cents"] else "-"),
    ])
    name = html.escape(tenant["name"])
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>{name} - AI guide report</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:0;background:#f6f7f9;color:#111}}
 header{{background:{html.escape(tenant['accent_color'])};color:#fff;padding:20px 24px}}
 main{{max-width:760px;margin:24px auto;padding:0 16px}}
 .g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
 .c{{background:#fff;border-radius:10px;padding:14px;border:1px solid #e3e5e8}}
 .c b{{display:block;font-size:26px}} .c span{{color:#666;font-size:13px}}
 section{{background:#fff;border-radius:10px;padding:14px;border:1px solid #e3e5e8;margin-top:16px}}
 table{{width:100%;border-collapse:collapse;font-size:13px}} td,th{{text-align:left;padding:6px;border-bottom:1px solid #eee}}
 small{{color:#666}}
</style></head><body>
<header><h1 style="margin:0">{name}</h1><small style="color:#fff;opacity:.85">AI guide results - last {s['days']} days</small></header>
<main>
<div class="g">{cards}</div>
<section><b>Daily activity</b> <small>grey = conversations, colour = leads</small>
<svg viewBox="0 0 600 115" width="100%" role="img" aria-label="Daily conversations and leads">{''.join(bars)}</svg></section>
<section><b>Recent leads</b><table><tr><th>Date</th><th>Who</th><th>What they wanted</th><th>Via</th><th>Status</th><th>Interest</th></tr>{rows or '<tr><td colspan=6>No leads yet.</td></tr>'}</table></section>
<p><small>Estimated pipeline = leads x the average lead value agreed with your provider. Contact details are not shown on this page.</small></p>
</main></body></html>"""
    return HTMLResponse(page)


# ------------------------------------------------------------ static UIs & Studio shell
@router.get("/admin-ui")
async def admin_ui():
    """Static dashboard shell. It holds no data; the page asks for the admin token and calls /admin/*."""
    return html_with_script_nonce(
        (_main().STATIC_DIR / "admin.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/", include_in_schema=False)
async def owner_root():
    """Types of the bare host: send people to the Studio, the customer sign-in.

    Before this, https://concierge.trendibizz.com/ answered 404 and a visitor had no way
    forward except guessing the path. Found by the 2026-11-14 site audit.
    """
    return RedirectResponse("/studio/", status_code=307)


@router.get("/favicon.ico", include_in_schema=False)
@router.get("/favicon.svg", include_in_schema=False)
async def owner_favicon():
    """Browsers ask for this on every page; a 404 was the only error in the owner app console."""
    icon = _main().STATIC_DIR / "favicon.svg"
    if not icon.is_file():
        return Response(status_code=204)
    return FileResponse(icon, media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/owner-ui")
async def owner_ui():
    return html_with_script_nonce(
        (_main().STATIC_DIR / "owner.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                 "Referrer-Policy": "no-referrer"},
    )


@router.get("/owner/qrcode.js", include_in_schema=False)
async def owner_qr_library():
    """The QR encoder the owner page uses to turn an invitation link into a scannable code.

    Served under /owner/ because that is the only prefix the public proxy forwards, and cached
    like a static asset: the file is part of the build, not customer data.
    """
    return FileResponse(_main().STATIC_DIR / "qrcode.js", media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=86400",
                                 "X-Content-Type-Options": "nosniff"})


@router.get("/studio", include_in_schema=False)
@router.get("/studio/", include_in_schema=False)
async def studio_page():
    return _studio_index(_main().STUDIO_DIR.resolve())


@router.get("/studio/assets/{path:path}", include_in_schema=False)
async def studio_asset(path: str):
    studio_dir = _main().STUDIO_DIR
    assets_root = (studio_dir / "assets").resolve()
    target = (assets_root / path).resolve()
    if not target.is_relative_to(assets_root):
        raise HTTPException(404, "Not found")
    if not _readable(target):
        raise HTTPException(404, "Not found")
    # Vite emits content-addressed filenames, so an asset can be cached forever: a new build
    # produces new names. Without this the browser guessed, and a tab opened before a deploy
    # asked for a chunk the deploy had already removed — the lazy-loaded page then went blank.
    return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable"})


def _readable(path) -> bool:
    """Can this file actually be opened right now?

    `is_file()` answers "does a regular file exist", which is not the same question. During a
    deploy the file exists but can be unreadable for a second (rsync writes it with the uploading
    user's permissions before the chmod), and the old code raised PermissionError straight out of
    the route: every request got a bare "Internal Server Error" instead of the app. Measured in
    production on 2026-11-14: eight 500s on /studio/index.html during one rsync.
    """
    try:
        if not path.is_file():
            return False
        with open(path, "rb"):
            return True
    except OSError:
        return False


def _studio_index(root):
    """Serve the shell, or say plainly that it is being updated. Never a 500."""
    index = root / "index.html"
    if _readable(index):
        return FileResponse(index, media_type="text/html",
                            headers={"Cache-Control": "no-store",
                                     "X-Robots-Tag": "noindex, nofollow, noai, noimageai"})
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8><title>One moment</title>"
        "<body style=\"font:16px system-ui;padding:48px;max-width:38rem;margin:auto\">"
        "<h1>One moment</h1><p>We are updating the app. Refresh this page in a few seconds.</p>",
        status_code=503, headers={"Retry-After": "5", "Cache-Control": "no-store"})


@router.get("/studio/install", include_in_schema=False)
@router.get("/studio/install/", include_in_schema=False)
async def studio_install():
    """The install page, served as its own document.

    It used to be a route inside the SPA, which meant a scan could land on the sign-in screen
    (a stored session, a stale bundle, or simply the auth gate) and ask for an email address —
    reported 2026-11-16 from a phone. This document has no router and no auth: the only thing it
    can be is the install offer.
    """
    studio_dir = _main().STUDIO_DIR
    target = (studio_dir / "install.html").resolve()
    if _readable(target):
        return html_with_script_nonce(
            target.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store",
                     "X-Robots-Tag": "noindex, nofollow, noai, noimageai"},
        )
    # A deploy that has not copied install.html yet still serves something sensible.
    return _studio_index(studio_dir.resolve())


_TICKET = re.compile(r"^[A-Za-z0-9_-]{20,100}$")


@router.get("/studio/manifest.webmanifest", include_in_schema=False)
async def studio_manifest(k: str = ""):
    """The app manifest, with the sign-in ticket carried into the installed app's start URL.

    iPhone gives a home-screen app its own empty storage, and the app launches at `start_url`.
    Putting the install-QR ticket in that URL's fragment lets the first launch sign itself in
    (the SPA already redeems `#invite=`), so there is no sign-in step to paste into. The ticket is
    one hour and the fragment never reaches a server log.
    """
    target = (_main().STUDIO_DIR / "manifest.webmanifest").resolve()
    if not _readable(target):
        raise HTTPException(404, "Not found")
    manifest = json.loads(target.read_text(encoding="utf-8"))
    if _TICKET.fullmatch(k or ""):
        manifest["start_url"] = f"/studio/#invite={k}"
    return Response(json.dumps(manifest), media_type="application/manifest+json",
                    headers={"Cache-Control": "no-store"})


@router.get("/studio/{path:path}", include_in_schema=False)
async def studio_file(path: str):
    root = _main().STUDIO_DIR.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not _readable(target):
        # A browser navigating to an app URL gets the shell; a missing *file* must be an honest
        # 404. Answering every missing path with index.html made /studio/sw.js a 200 text/html
        # document: a browser still holding the old worker fetches it for an update, rejects it on
        # the MIME type, and the stale worker can never be replaced (measured live 2026-11-15,
        # against the previous record's claim that the old worker URL 404'd). The SPA has no
        # client-side routes, so no real page lives at a path with a dot in its last segment.
        name = path.rsplit("/", 1)[-1]
        if "." in name:
            raise HTTPException(404, "Not found")
        return _studio_index(root)
    if path.endswith('sw-v2.js'):
        # The worker script must be revalidated on every visit, or a cached copy keeps a browser on
        # an old build indefinitely (measured: Cloudflare served a HIT with no Cache-Control at all).
        return FileResponse(target, media_type="text/javascript",
                            headers={"Cache-Control": "no-cache",
                                     "Service-Worker-Allowed": "/studio/"})
    return FileResponse(target)


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return Response("User-agent: *\nDisallow: /\n", media_type="text/plain",
                    headers={"Cache-Control": "public, max-age=300"})


@router.get("/onboarding", include_in_schema=False)
async def onboarding_page():
    return html_with_script_nonce(
        (_main().STATIC_DIR / "onboarding.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                 "Referrer-Policy": "no-referrer"},
    )


class SiteEnquiry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["seo", "concierge", "security"]
    email: str = Field(max_length=320)
    name: str = Field(default="", max_length=120)
    website: str = Field(default="", max_length=300)
    message: str = Field(default="", max_length=4000)
    plan: str = Field(default="", max_length=20)
    channels: list[str] = Field(default_factory=list, max_length=12)
    referral: str = Field(default="", max_length=64)
    trap: str = Field(default="", max_length=200)


@router.post("/api/enquiry", include_in_schema=False)
async def website_enquiry(body: SiteEnquiry, request: Request):
    """The public website's enquiry forms. No account; stored first, emailed second."""
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else "")
    try:
        return await site_enquiry.submit(
            **body.model_dump(), ip=ip, user_agent=request.headers.get("user-agent", ""))
    except site_enquiry.Refused as error:
        raise HTTPException(error.status, str(error)) from None


@router.get("/api/robots", include_in_schema=False)
async def robots_check(request: Request, url: str = ""):
    """The public AI-robots checker's fetch: https://<host>/robots.txt as text/plain (see robots_fetch)."""
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else "unknown")
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Trendi-Served-By": "api"}
    if not robots_fetch.limiter.check(ip):
        return JSONResponse({"error": "rate_limited", "message": "Too many checks. Try again in a minute."},
                            status_code=429, headers={**headers, "Retry-After": "60"})
    try:
        text, source, truncated = await robots_fetch.fetch_robots(url)
    except robots_fetch.RobotsError as error:
        return JSONResponse({"error": error.code, "message": error.message}, status_code=error.status, headers=headers)
    return Response(text, media_type="text/plain", headers={
        **headers, "X-Trendi-Source": source, "X-Trendi-Truncated": "1" if truncated else "0"})


# The public site tools (website/tools/site-check.js and security-check.js). They were served only by the untracked
# deploy_known_good/_worker.js on the box; see site_tools.py for the contract and limits.
# X-Trendi-Served-By lets the smoke test and health check tell this API from any legacy file answering the same path.
_TOOL_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Trendi-Served-By": "api"}
_TOOL_CORS = {"access-control-allow-origin": "https://trendibizz.com", "access-control-allow-methods": "POST, OPTIONS",
              "access-control-allow-headers": "content-type", "access-control-max-age": "86400"}


def _visitor_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


async def _run_tool(request: Request, limiter, runner):
    if not limiter.check(_visitor_ip(request)):
        return JSONResponse({"error": "rate_limited", "message": site_tools.RATE_MESSAGE}, status_code=429, headers=_TOOL_HEADERS)
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        return JSONResponse({"error": "bad_json", "message": "POST JSON { url }."}, status_code=400, headers=_TOOL_HEADERS)
    try:
        return JSONResponse(await runner(body.get("url")), headers=_TOOL_HEADERS)
    except site_tools.ToolError as error:
        return JSONResponse({"error": error.code, "message": error.message, **error.extra}, status_code=error.status, headers=_TOOL_HEADERS)


@router.get("/api/site-check", include_in_schema=False)
async def site_check_info():
    return JSONResponse({"ok": True, "endpoint": "/api/site-check", "method": "POST", "body": {"url": "https://example.com"}}, headers=_TOOL_HEADERS)


@router.options("/api/site-check", include_in_schema=False)
@router.options("/api/security-check", include_in_schema=False)
async def site_tools_options():
    return Response(status_code=204, headers=_TOOL_CORS)


@router.post("/api/site-check", include_in_schema=False)
async def site_check_run(request: Request):
    return await _run_tool(request, site_tools.site_limiter,
                           lambda url: site_tools.site_check(url, site_tools.pagespeed_key()))


@router.get("/api/security-check", include_in_schema=False)
async def security_check_info():
    return JSONResponse({"ok": True, "endpoint": "/api/security-check", "method": "POST", "body": {"url": "https://example.com"},
                         "honesty": "Light check \u2260 penetration testing. Presence/absence only. Not a hack-proof guarantee."}, headers=_TOOL_HEADERS)


@router.post("/api/security-check", include_in_schema=False)
async def security_check_run(request: Request):
    return await _run_tool(request, site_tools.security_limiter, site_tools.security_check)
