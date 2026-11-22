"""N5b Studio Parity regression tests."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_studio_unified_inbox_has_email_phone_voicemail_and_chat():
    texts = (REPO_ROOT / "web/portal/src/Texts.tsx").read_text(encoding="utf-8")
    for needle in (
        "/owner/sms/inbox",
        "/owner/chat/inbox",
        "/owner/email-drafts",
        "/owner/phone-calls",
        "/owner/voice-recordings/",
        "<audio controls",
    ):
        assert needle in texts, f"Missing {needle} in unified inbox Texts.tsx"


def test_studio_has_invoices_tab_push_opt_in_and_five_hidden_top_tabs():
    app_tsx = (REPO_ROOT / "web/portal/src/App.tsx").read_text(encoding="utf-8")
    invoices_tsx = (REPO_ROOT / "web/portal/src/Invoices.tsx").read_text(encoding="utf-8")
    assert "/owner/invoices" in invoices_tsx
    assert "/owner/push/subscribe" in app_tsx
    for tab in ("pipeline", "texts", "companies", "permissions", "replies", "invoices"):
        assert f'<Tab value="{tab}"' in app_tsx, f"Top TabList missing {tab}"


def test_owner_html_retires_dead_media_studio_buttons():
    html = (REPO_ROOT / "api/static/owner.html").read_text(encoding="utf-8")
    for dead_id in ('id="media-image"', 'id="media-video"', 'id="media-ai"'):
        assert dead_id not in html, f"Dead Media Studio button {dead_id} still present in owner.html"
    assert 'id="media-save-brand"' in html
