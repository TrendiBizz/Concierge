#!/usr/bin/env python3
"""Generate website/help.html (Concierge help and onboarding hub) and add the
"Need help?" banner and footer link to the other pages.

Run from repo root:  python3 scripts/seo/make_help_page.py
Idempotent. Banner links are text links, not .btn: link_audit.py flags .btn loops
(contact -> help -> contact via the header button). Head, header, footer and scripts are cloned from website/guide.html so the hub
inherits the site template (and the single widget.js script the a2ui test requires).
Facts come only from guide.html; no response-time or result promises.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "website"
DATE = "2026-11-27"
DATE_HUMAN = "27 November 2026"
URL = "https://trendibizz.com/help"
TITLE = "Concierge Help and Onboarding | Trendi"
DESC = ("Help for setting up Trendi Concierge: seven short captioned stage videos, "
        "the full walkthrough, and how to ask us to set it up with you.")

STAGES = [
    (1, "Business identity and approved knowledge", 36),
    (2, "Owner alerts, takeover and pause", 38),
    (3, "Website chat and browser voice", 28),
    (4, "Bookings and calendar sync", 28),
    (5, "Phone, voicemail and missed-call text-back", 39),
    (6, "Email, SMS and connected software", 28),
    (7, "Go-live scorecard and daily workflow", 38),
]

BANNER_MARK = "help-banner"
BANNER = ('<section class="section--surface design-section help-banner"><div class="wrap"><p>'
          '<strong>Need help setting up?</strong> Watch the step-by-step setup videos or ask us. '
          '<a class="refresh-text-link" href="/help">Help and onboarding</a> '
          '<a class="refresh-text-link" href="/contact">Contact us</a></p></div></section>\n')
BANNER_PAGES = ["guide", "concierge", "concierge-start", "contact", "pricing"]

PLUS = ('<svg aria-hidden="true" class="ui-icon" viewbox="0 0 20 20"><path d="M10 4v12"></path>'
        '<path class="plus-line" d="M4 10h12"></path></svg>')
FAQ = [
    ("Can Trendi set this up for me?",
     "Yes. Our team can configure any stage with you. Use Request guided setup and we will agree what to configure and test first."),
    ("How long does setup take?",
     "The guide estimates about 3 to 5 minutes for each of the 7 stages. Your own timing depends on which channels you enable and which providers serve your country."),
    ("What if I need to stop Concierge quickly?",
     "Use the Global Pause Switch at the top of Studio. To step back for one customer, reply once in Inbox and Concierge steps back for that customer (Per-Customer Takeover)."),
    ("Will Concierge make up a price?",
     "No. Price Guard stops Concierge from inventing a quote. Test it in the Sandbox Test Chat before going live."),
]


def video_figure(n, name, secs):
    return (f'<figure class="media-video" id="stage-{n}">\n'
            f'<h3>Stage {n}: {name}</h3>\n'
            f'<video controls="" height="720" playsinline="" poster="/media/help/stage-{n}-poster.jpg" preload="none" width="1280">\n'
            f'<source src="/media/help/stage-{n}.mp4" type="video/mp4"/>\n'
            f'<track default="" kind="captions" label="English" src="/media/help/stage-{n}.vtt" srclang="en"/>\n'
            'Your browser does not support the video tag.\n</video>\n'
            f'<figcaption>{name} ({secs} seconds, with captions). '
            f'<a href="/guide#stage-{n}">Read the written steps</a>.</figcaption>\n</figure>\n')


def schema():
    vids = [{
        "@type": "VideoObject", "@id": f"{URL}#help-stage-{n}-video",
        "name": f"Concierge setup stage {n}: {name}",
        "description": f"Short captioned screen walkthrough of stage {n} of the Concierge Setup & Onboarding Hub: {name.lower()}.",
        "thumbnailUrl": f"https://trendibizz.com/media/help/stage-{n}-poster.jpg",
        "uploadDate": f"{DATE}T00:00:00+13:00",
        "contentUrl": f"https://trendibizz.com/media/help/stage-{n}.mp4",
        "embedUrl": f"{URL}#stage-{n}", "inLanguage": "en", "duration": f"PT{secs}S",
        "publisher": {"@type": "Organization", "@id": "https://trendibizz.com/#organization", "name": "Trendi", "url": "https://trendibizz.com/"},
    } for n, name, secs in STAGES]
    graph = [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://trendibizz.com/"},
            {"@type": "ListItem", "position": 2, "name": "Concierge", "item": "https://trendibizz.com/concierge"},
            {"@type": "ListItem", "position": 3, "name": "Help and onboarding", "item": URL}]},
        {"@type": "WebPage", "@id": URL + "#webpage", "url": URL, "name": "Concierge help and onboarding",
         "description": DESC, "dateModified": DATE, "inLanguage": "en",
         "publisher": {"@type": "Organization", "name": "Trendi"}},
    ] + vids
    return '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":")) + "</script>"


def build():
    g = (WEB / "guide.html").read_text()
    head = g[:g.index("<main")]
    head = re.sub(r"<title>.*?</title>", f"<title>{TITLE}</title>", head, flags=re.S)
    head = re.sub(r'(<meta content=")[^"]*(" name="description"/>)', lambda m: m.group(1) + DESC + m.group(2), head)
    head = head.replace("https://trendibizz.com/guide", URL)
    head = re.sub(r'(<meta content=")[^"]*(" property="og:title"/>)', lambda m: m.group(1) + TITLE + m.group(2), head)
    head = re.sub(r'(<meta content=")[^"]*(" property="og:description"/>)', lambda m: m.group(1) + DESC + m.group(2), head)
    head = re.sub(r'<script type="application/ld\+json">.*?</script>', lambda m: schema(), head, flags=re.S)
    tail = g[g.index("</main>"):]
    faq = "".join(f"<details><summary>{q}{PLUS}</summary><p>{a}</p></details>" for q, a in FAQ)
    figs = "".join(video_figure(*s) for s in STAGES)
    main = f'''<main id="main">
<section class="hero refresh-home design-section"><div class="wrap">
<h1>Concierge help and onboarding</h1>
<p class="lead">Everything for getting Trendi Concierge set up: a short captioned video for each setup stage, the full walkthrough, and a way to ask us for help.</p>
<div class="cta-row"><a class="btn lime" href="/concierge-start?plan=monthly">Request guided setup</a><a class="refresh-text-link" href="https://concierge.trendibizz.com/studio/">Open Studio Onboarding Hub</a></div>
<p class="fine">USD $199/month, 3-month minimum, then month to month.</p>
</div></section>
<section class="section--surface design-section" id="need-help"><div class="wrap">
<h2>Need help right now?</h2>
<p class="section-lead">Email <a href="mailto:admin@trendibizz.com">admin@trendibizz.com</a> or use the <a href="/contact">contact page</a>. Tell us which stage you are on and what you see, and we will reply to you.</p>
</div></section>
<section class="design-section" id="setup-path"><div class="wrap">
<h2>The setup path</h2>
<ol class="steps">
<li><h3>Request setup</h3><p>Ask for <a href="/concierge-start?plan=monthly">guided setup</a>, or sign in to Studio if you already have a workspace.</p></li>
<li><h3>Work through the 7 stages</h3><p>The Setup &amp; Onboarding Hub in Studio tracks your progress and runs checks at each step. Our team can configure any stage with you.</p></li>
<li><h3>Test, then go live</h3><p>Use the Sandbox Test Chat and the Readiness Scorecard, then click Launch Concierge when you are ready.</p></li>
</ol>
</div></section>
<section class="section--surface design-section" id="video-walkthrough"><div class="wrap">
<h2>Watch the full walkthrough</h2>
<p class="section-lead">Real screens from start to finish, about three minutes. <a href="/guide#video-walkthrough">Open it on the setup guide</a>.</p>
</div></section>
<section class="design-section" id="stage-videos"><div class="wrap">
<h2>Setup help, one video per stage</h2>
<p class="section-lead">Each video is under 40 seconds, uses demo data and has English captions.</p>
{figs}</div></section>
<section class="section--surface design-section" id="faq"><div class="wrap">
<h2>Questions</h2>
{faq}</div></section>
<section class="design-section"><div class="wrap">
<h2>Related</h2>
<p><a href="/guide">Complete setup guide</a>, <a href="/concierge">Concierge</a>, <a href="/pricing">Pricing</a>, <a href="/contact">Contact</a></p>
<p class="fine" data-updated="{DATE}">Reviewed by the Trendi team, Last updated {DATE_HUMAN}</p>
</div></section>
'''
    (WEB / "help.html").write_text(head + main + tail)


def patch_pages():
    n_foot = n_ban = 0
    anchor = '<nav aria-label="Explore" class="footer-nav">'
    link = '<a href="/help">Help and onboarding</a>'
    for p in sorted(WEB.glob("**/*.html")):
        t = p.read_text()
        o = t
        if anchor in t and link not in t:
            i = t.index(anchor)
            j = t.index("</nav>", i)
            seg = t[i:j]
            old = '<a href="/concierge">Concierge</a>'
            if old in seg:
                seg = seg.replace(old, old + link, 1)
            else:  # pages with a different footer: after the first link
                k = seg.index("</a>") + 4
                seg = seg[:k] + link + seg[k:]
            t = t[:i] + seg + t[j:]
            n_foot += 1
        if p.parent == WEB and p.stem in BANNER_PAGES and BANNER_MARK not in t:
            t, k = re.subn(r'(<main[^>]*id="main"[^>]*>)', lambda m: m.group(1) + "\n" + BANNER, t, count=1)
            n_ban += k
        if t != o:
            p.write_text(t)
    print(f"footer links added: {n_foot}; banners added: {n_ban}")


if __name__ == "__main__":
    build()
    patch_pages()
