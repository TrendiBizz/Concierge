#!/usr/bin/env python3
"""Send the Pukeko case-study permission request (pitches/pukeko.md). Runs ON the box like send_followups.py. Approved by Jo 2026-11-25."""
import smtplib, ssl
from email.message import EmailMessage
from pathlib import Path
BODY = """Hi Conrad,

You've been using Concierge for a while. Would you be OK with us writing a short case study, with a link to Pukeko's site? Nothing goes live until you've read and approved it in writing.

To make it real, three or four numbers would help (only what you're comfortable sharing): enquiries captured per week, how many came after hours, time saved on quotes, and one thing you'd tell another builder.

If yes, just reply "OK to feature" and I'll send a draft.

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
    m = EmailMessage(); m["From"] = "Jo at Trendi <admin@trendibizz.com>"; m["To"] = "conrad@pukekoconstruction.co.nz"
    m["Reply-To"] = "admin@trendibizz.com"; m["Subject"] = "Can we feature Pukeko as a Concierge case study?"; m.set_content(BODY)
    _ok(m["To"]); s.send_message(m); print("sent pukeko")
