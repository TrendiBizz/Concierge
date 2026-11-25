#!/usr/bin/env python3
"""Generate the 2026-11-25 keyword-gap pages by cloning website/missed-call-text-back.html.

The site is hand-written static HTML; this keeps the shared head, header and footer identical to the
template and swaps only the title, description, schema, and <main>. Run:  python3 scripts/seo/make_page.py
Then:  python3 scripts/seo/site_seo.py sitemap --write && python3 scripts/seo/site_seo.py check
Every competitor fact on a page must be dated and sourced in QA/verification (see COMPETITORS_RAW_2026-11-12.md).
"""
import html, json, re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "website"
TEMPLATE = (WEB / "missed-call-text-back.html").read_text(encoding="utf-8")
DATE, DATE_LONG = "2026-11-25", "25 November 2026"
BASE = "https://trendibizz.com"
RELATED = ('<a href="/ai-office">AI receptionist and AI office overview</a> · <a href="/virtual-receptionist">Virtual receptionist</a> · '
           '<a href="/missed-call-text-back">Missed-call text back</a> · <a href="/after-hours-answering">After-hours answering</a> · '
           '<a href="/ai-answering-service-vs-human">AI answering service vs human</a> · <a href="/ai-office-cost">AI office cost</a> · '
           '<a href="/pricing">Pricing</a> · <a href="/concierge">Concierge</a> · <a href="/best-ai-office">How to choose an AI receptionist</a>')
PRICE = ('<section class="section--surface design-section" id="price"><div class="wrap"><h2>Pricing</h2><div class="pricing-grid two">'
         '<article class="pricing featured"><h3>Monthly</h3><p class="price"><span class="currency">USD</span> $199<small>/ month</small></p>'
         '<p class="terms">3-month minimum, then monthly. Phone and SMS provider charges are separate.</p>'
         '<a class="btn lime" href="/concierge-start">Request setup</a></article></div></div></section>')

def sections(blocks):
    return "".join(f'<section class="design-section"><div class="wrap"><h2>{h}</h2>{body}</div></section>' for h, body in blocks)

def build(slug, title, desc, eyebrow, h1, lead, blocks, faqs):
    url = f"{BASE}/{slug}"
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": title, "item": url}]},
        {"@type": "WebPage", "@id": url + "#webpage", "url": url, "name": title,
         "isPartOf": {"@id": BASE + "/#website"}, "dateModified": DATE},
        {"@type": "Service", "name": "Concierge AI office", "serviceType": "AI office for small business",
         "provider": {"@id": BASE + "/#organization"}, "areaServed": [{"@type": "Country", "name": "New Zealand"}, "Worldwide"],
         "url": url, "offers": {"@type": "Offer", "price": "199", "priceCurrency": "USD"}},
        {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]}]}
    faq_html = "".join(f"<details><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>" for q, a in faqs)
    main = ('<main id="main"><section class="hero refresh-home design-section"><div class="wrap hero-grid"><div>'
            f'<p class="eyebrow">{eyebrow}</p><h1>{h1}</h1><p class="lead">{lead}</p>'
            '<div class="cta-row"><a class="btn lime" href="/concierge-start">Request setup</a><a class="refresh-text-link" href="/pricing">See plans and pricing →</a></div>'
            '<p class="fine">Channels are configured and tested before activation. We do not promise leads, sales or rankings.</p></div></div></section>'
            + sections(blocks) + PRICE
            + f'<section class="design-section" id="faq"><div class="wrap"><h2>Questions</h2>{faq_html}</div></section>'
            + f'<section class="section--surface design-section"><div class="wrap"><h2>Related</h2><p>{RELATED}</p>'
              f'<p class="fine" data-updated="{DATE}">Reviewed by the Trendi team · Last updated {DATE_LONG}</p></div></section></main>')
    t = TEMPLATE
    esc = html.escape(title, quote=False)
    t = re.sub(r"<title>.*?</title>", f"<title>{esc}</title>", t, count=1)
    t = re.sub(r'(<meta content=")[^"]*(" name="description"/>)', lambda m: m.group(1) + html.escape(desc) + m.group(2), t, count=1)
    t = re.sub(r'(<meta content=")[^"]*(" property="og:title"/>)', lambda m: m.group(1) + html.escape(title) + m.group(2), t, count=1)
    t = re.sub(r'(<meta content=")[^"]*(" property="og:description"/>)', lambda m: m.group(1) + html.escape(desc) + m.group(2), t, count=1)
    t = t.replace(BASE + "/missed-call-text-back", url)
    t = re.sub(r'<script type="application/ld\+json">.*?</script>', lambda m: '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False, separators=(",", ":")) + "</script>", t, count=1, flags=re.S)
    t = re.sub(r'<main id="main">.*?</main>', lambda m: main, t, count=1, flags=re.S)
    (WEB / f"{slug}.html").write_text(t, encoding="utf-8")
    print("wrote", slug)

build("ai-answering-service",
  "AI answering service for small business | Trendi",
  "An AI answering service that picks up calls, texts, email and website chat, captures the enquiry and books the job. USD $199 a month, set up and tested for you.",
  "AI ANSWERING SERVICE", "AI answering service for small business",
  "Concierge is an AI answering service for the calls you cannot take: it answers in your business name, captures who called and why, books where your calendar allows, and hands the enquiry to your team.",
  [("What an AI answering service does",
    "<p>A traditional answering service is a call centre that takes a message. An AI answering service answers the call itself, asks the questions you set, answers routine questions from your own information, and records the enquiry in a CRM with a transcript.</p>"
    "<p>Concierge covers the phone, website chat, email and SMS from one place, so a customer who rings, then texts, then emails is one conversation, not three.</p>"),
   ("When it answers, and when a person should",
    "<p>You choose the hours and the rules: after hours only, when you are busy, or always. Anything the assistant should not decide, such as a complaint, a quote outside your price list or a safety issue, is flagged for you to follow up rather than guessed at.</p>"
    "<p>Compare the trade-offs in <a href=\"/ai-answering-service-vs-human\">AI answering service vs a human service</a>.</p>"),
   ("What we set up with you",
    "<p>A business phone number, your opening hours, your services and prices, the questions to ask on every call, your calendar, and who is told when something needs a person. Each channel is tested before it goes live. If a channel cannot be tested in your country, we tell you before you pay.</p>")],
  [("Is an AI answering service the same as a virtual receptionist?", "They overlap. A virtual receptionist is usually a person working remotely. Concierge is an AI assistant that answers for you and passes on what needs a human. See the virtual receptionist page for the comparison."),
   ("How much does it cost?", "Concierge is USD $199 a month with a 3-month minimum. Phone and SMS provider charges are separate."),
   ("Does it answer calls in my business name?", "Yes, once a number and voice provider are connected and tested. The greeting, tone and what it may say are agreed with you."),
   ("What if a caller needs a person?", "Anything outside the rules you set is recorded and flagged for you to follow up."),
   ("Does it guarantee more customers?", "No. It reduces missed enquiries and records them properly. We do not promise leads, sales or rankings.")])

build("ai-phone-answering",
  "AI phone answering for small business | Trendi",
  "AI phone answering that picks up business calls, answers common questions, takes details and books, with a transcript of every call. USD $199 a month.",
  "AI PHONE ANSWERING", "AI phone answering for small business",
  "Concierge answers your business phone with an AI assistant: it greets callers in your business name, answers from your own information, takes details and books, and leaves you a transcript.",
  [("How the phone is answered",
    "<p>You get a dedicated business phone number. When a call arrives in the hours you set, the assistant answers, finds out what the caller needs, and either resolves it or records it for you.</p>"
    "<p>Every call produces a transcript and an enquiry in your CRM, with the caller number and time, so nothing depends on someone remembering to ring back.</p>"),
   ("Calls you miss anyway",
    "<p>If a call is not answered, for example because it was not forwarded or the line was down, an SMS follow-up can be configured with your provider. See <a href=\"/missed-call-text-back\">missed-call text back</a> for how that works and its limits.</p>"),
   ("What it is not",
    "<p>It is not a promise that every caller becomes a customer. Anything outside the rules you set is recorded for you to follow up.</p>")],
  [("Can I keep my existing phone number?", "Ask us during setup. Whether an existing number can be forwarded or moved depends on your provider and country."),
   ("Does it work after hours?", "Yes. You choose the hours. Many customers use it only outside opening hours or when the phone is busy."),
   ("Will callers know it is an AI?", "The greeting wording, including how the assistant introduces itself, is agreed with you during setup."),
   ("What does it cost?", "USD $199 a month with a 3-month minimum. Call and SMS charges from the provider are separate."),
   ("Does it work in New Zealand?", "Yes, Trendi is New Zealand based. Each channel is tested for your country before activation.")])

build("gohighlevel-alternative",
  "GoHighLevel alternative for small business: Concierge vs GoHighLevel | Trendi",
  "Concierge vs GoHighLevel: an AI receptionist and CRM at USD $199 a month, against a marketing platform built for agencies. Where each fits.",
  "COMPARISON", "A GoHighLevel alternative for small business",
  "GoHighLevel is a broad marketing and CRM platform, built largely for agencies. Concierge is narrower: an AI receptionist and office assistant for one business. This page says where each fits.",
  [("The short version",
    "<p>Choose GoHighLevel if you run an agency that wants funnels, courses, white-label and resale in one platform and has the time to configure it. Choose Concierge if you are a trade, clinic, agency-free small business that wants calls, chat, email and SMS answered, enquiries captured and bookings made, set up and tested for you.</p>"),
   ("Price, as published",
    "<p>From GoHighLevel's own pricing page (checked 12 November 2026): Starter USD $97, Unlimited $297 and Founder $497 a month, with a 14-day trial. The subscription buys the platform; usage is metered separately through a wallet, for example premium workflow actions at $0.01 per execution, and its voice and conversation AI agents are billed on top of the plan. Check the current figures at <a href=\"https://www.gohighlevel.com/pricing\" rel=\"nofollow noopener\">gohighlevel.com/pricing</a>, as vendors change them.</p>"
    "<p>Concierge is one price, USD $199 a month with a 3-month minimum, including setup, testing, a business phone number, voice answering, SMS and email confirmations, voicemail, CRM and integrations. Provider charges for calls and SMS are separate.</p>"),
   ("What you do not get from Concierge",
    "<p>No funnel builder, no courses or communities, no white-label or resale mode and no affiliate manager. If you need those, GoHighLevel is the better fit and we will say so. We keep Concierge small on purpose so that the part that matters to a small business, answering and following up every enquiry, is the part that is set up properly.</p>"),
   ("Who sets it up",
    "<p>Concierge is configured and tested with you before activation: your services, hours, prices, questions, calendar and who is told when. You do not build workflows.</p>")],
  [("Is Concierge a GoHighLevel replacement?", "For the receptionist, enquiry capture, follow-up and booking part, yes. For funnels, courses, communities and agency resale, no."),
   ("How much does GoHighLevel cost compared with Concierge?", "GoHighLevel's published plans are USD $97, $297 and $497 a month plus metered usage (checked 12 November 2026). Concierge is USD $199 a month with a 3-month minimum, with provider call and SMS charges separate."),
   ("Can I move from GoHighLevel to Concierge?", "Your knowledge base is built by reading your website. Ask us what else can be moved in your case."),
   ("Does Concierge have a CRM?", "Yes, a built-in CRM with enquiries, follow-ups and bookings, and one conversation history per customer across channels."),
   ("Do you guarantee results?", "No. We do not promise leads, sales, rankings or AI mentions.")])
