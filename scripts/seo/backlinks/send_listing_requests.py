#!/usr/bin/env python3
"""Send the directory listing-request emails from admin@trendibizz.com (Brevo SMTP).

Runs ON the box (reads /opt/trendi/shared/api.env; never prints secrets). From the repo:
  ssh -i Concierge root@152.42.239.240 python3 - < scripts/seo/backlinks/send_listing_requests.py
Text comes only from listing-kit.md facts. Approved by Jo 2026-11-25.
"""
import smtplib, ssl
from email.message import EmailMessage
from pathlib import Path

TARGETS = [
    (31, "hello@shouldiuse.io", "ShouldIUse"),
    (36, "hello@thetoolregister.com", "The Tool Register"),
]
BODY = """Hello,

Could you consider listing Trendi Concierge on {site}?

Name: Trendi Concierge (by TRENDI LIMITED, New Zealand)
URL: https://trendibizz.com/concierge
One line: AI receptionist for small business: answers calls, chat, email and SMS, captures every enquiry.
Description: Concierge answers your business calls, website chat, email and SMS, records each enquiry in a built-in CRM, and books where your calendar allows. Set up and tested for you.
Pricing: USD $199 a month, 3-month minimum; provider call and SMS charges separate.
Markets: New Zealand and worldwide.
Logo: https://trendibizz.com/brand/logo-refresh.svg
Comparisons we publish, with dated sources: https://trendibizz.com/gohighlevel-alternative

If you have a submission form or a different format you prefer, tell me and I will use it. Thank you.

Jo
Trendi
https://trendibizz.com
"""

def load(path="/opt/trendi/shared/api.env"):
    out = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out

env = load()
ctx = ssl.create_default_context()
# Do-not-contact guard (mirrors backlinks/do-not-contact.csv; tested by test_do_not_contact.py)
DNC = ("techday.co.nz", "techday.com", "receptionistindex.com", "receptionistratings.com")
def _ok(to):
    d = str(to).lower().rsplit("@", 1)[-1].strip(" >")
    if any(d == b or d.endswith("." + b) for b in DNC):
        raise SystemExit("REFUSED: " + str(to) + " is on the do-not-contact list")
with smtplib.SMTP(env["SMTP_HOST"], int(env.get("SMTP_PORT", "587")), timeout=30) as s:
    s.starttls(context=ctx)
    s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
    for pid, to, site in TARGETS:
        m = EmailMessage()
        m["From"] = "Jo at Trendi <admin@trendibizz.com>"
        m["To"] = to
        m["Reply-To"] = "admin@trendibizz.com"
        m["Subject"] = "Listing request: Trendi Concierge (AI receptionist)"
        m.set_content(BODY.format(site=site))
        _ok(m["To"]); s.send_message(m)
        print("sent", pid, to)
