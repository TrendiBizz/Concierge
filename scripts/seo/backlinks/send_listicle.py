#!/usr/bin/env python3
"""Send the listicle inclusion pitch to receptionistratings.com (contact dor@ is published on its homepage). Runs ON the box. Approved by Jo 2026-11-25. Text = pitches/listicles.md."""
import smtplib, ssl
from email.message import EmailMessage
from pathlib import Path
BODY = """Hi,

I read your AI receptionist ratings. One addition for your readers: Trendi Concierge answers a small business's calls, web chat, email and SMS, logs each enquiry in a built-in CRM, and books where the calendar allows. It is set up and tested for the customer; USD $199/month, 3-month minimum (call/SMS carrier charges separate). NZ-based, serves worldwide.

Details: https://trendibizz.com/concierge
Happy to give screenshots, a demo number or any fact you want to verify.

Thanks,
Jo
Trendi
https://trendibizz.com
"""
env = {}
for l in Path("/opt/trendi/shared/api.env").read_text().splitlines():
    l = l.strip()
    if l and not l.startswith("#") and "=" in l:
        k, _, v = l.partition("="); env[k.strip()] = v.strip().strip('"').strip("'")
# Do-not-contact guard (mirrors backlinks/do-not-contact.csv; tested by test_do_not_contact.py)
DNC = ("techday.co.nz", "techday.com")
def _ok(to):
    d = str(to).lower().rsplit("@", 1)[-1].strip(" >")
    if any(d == b or d.endswith("." + b) for b in DNC):
        raise SystemExit("REFUSED: " + str(to) + " is on the do-not-contact list")
with smtplib.SMTP(env["SMTP_HOST"], int(env.get("SMTP_PORT", "587")), timeout=30) as s:
    s.starttls(context=ssl.create_default_context()); s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
    m = EmailMessage(); m["From"] = "Jo at Trendi <admin@trendibizz.com>"; m["To"] = "dor@receptionistratings.com"
    m["Reply-To"] = "admin@trendibizz.com"; m["Subject"] = "Suggestion for your AI receptionist ratings: Trendi Concierge"; m.set_content(BODY)
    _ok(m["To"]); s.send_message(m); print("sent listicle")
