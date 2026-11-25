#!/usr/bin/env python3
"""Send the 4 NZ press follow-ups (drafts in pitches/followups.md) from admin@trendibizz.com via Brevo SMTP.
Runs ON the box: ssh -i Concierge root@152.42.239.240 python3 - < scripts/seo/backlinks/send_followups.py
Approved by Jo 2026-11-25."""
import smtplib, ssl
from email.message import EmailMessage
from pathlib import Path

URL = "https://trendibizz.com/research/ai-crawler-blocking-2026"
SIGN = "\n\nThanks,\nJo\nTrendi\nhttps://trendibizz.com\n"
MSGS = [
    (1, "editor@nzentrepreneur.co.nz", "Re: Data: how 100 SaaS sites treat AI crawlers",
     "Kia ora,\n\nA quick nudge on the note I sent last week. One line for your readers: of 94 readable B2B/SaaS sites, only 2 block any major AI crawler. Method, data and CSV: " + URL + "\n\nHappy to send a short founder-focused comment."),
    (2, "editors@techday.com", "Re: New Zealand study: AI crawler access on 100 SaaS sites",
     "Hi,\n\nFollowing up on last week's note. The study covers sites across NZ, AU, UK and US and is fully reproducible: " + URL + "\n\nI can send the CSV or a NZ-only cut if useful."),
    (5, "info@businessdesk.co.nz", "Re: Data: only 2 of 94 SaaS sites block a major AI crawler",
     "Hi,\n\nFollowing up on last week's note. Only 2 of 94 readable B2B/SaaS sites block any of 12 major AI crawlers, and 35 of 100 publish an llms.txt. Method and raw data: " + URL + "\n\nI can send the CSV or a short comment."),
    (6, "news@interest.co.nz", "Re: Data: AI crawler access across 100 SaaS sites",
     "Hi,\n\nA short follow-up to last week's note. Data on how 100 well-known SaaS sites treat AI crawlers, with method and CSV: " + URL + "\n\nHappy to supply a NZ-only cut."),
]
env = {}
for line in Path("/opt/trendi/shared/api.env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
with smtplib.SMTP(env["SMTP_HOST"], int(env.get("SMTP_PORT", "587")), timeout=30) as s:
    s.starttls(context=ssl.create_default_context())
    s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
    for pid, to, subj, body in MSGS:
        m = EmailMessage()
        m["From"] = "Jo at Trendi <admin@trendibizz.com>"
        m["To"] = to
        m["Reply-To"] = "admin@trendibizz.com"
        m["Subject"] = subj
        m.set_content(body + SIGN)
        s.send_message(m)
        print("sent", pid, to)
