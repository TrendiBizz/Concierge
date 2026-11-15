#!/usr/bin/env python3
"""Rebuild staged pages from the clean live snapshot. Idempotent: always starts from live-snapshot/site-clean."""
import json, re, shutil, os, html
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'live-snapshot', 'site-clean')
DST = os.path.join(ROOT, 'site')
ICON = '<svg aria-hidden="true" class="ui-icon" viewbox="0 0 20 20"><path d="M10 4v12"></path><path class="plus-line" d="M4 10h12"></path></svg>'
TODAY = '2026-11-15'
REVIEWED = '<p class="fine" data-updated="2026-11-15">Reviewed by the Trendi team · Last updated 15 November 2026</p>'

def faq_html(qas):
    return ''.join(f'<details><summary>{html.escape(q, quote=False)}{ICON}</summary><p>{html.escape(a, quote=False)}</p></details>' for q, a in qas)

def once(s, old, new, label):
    n = s.count(old)
    assert n == 1, f'{label}: anchor found {n} times'
    return s.replace(old, new)

def patch_jsonld(s, qas, label):
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', s, re.S)
    assert m, label
    data = json.loads(m.group(1))
    graph = data.get('@graph', [data])
    seen = {'faq': False, 'page': False}
    for node in graph:
        if node.get('@type') == 'FAQPage':
            for q, a in qas:
                node['mainEntity'].append({'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}})
            seen['faq'] = True
        if node.get('@type') == 'WebPage':
            node['dateModified'] = TODAY
            seen['page'] = True
    assert seen['faq'], label + ' no FAQPage'
    new = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    return s[:m.start(1)] + new + s[m.end(1):]

def figure(src, w, h, alt, cap):
    return (f'<figure class="media-video"><img src="{src}" width="{w}" height="{h}" alt="{html.escape(alt)}" loading="lazy" decoding="async"/>'
            f'<figcaption>{cap}</figcaption></figure>')

CHAT_FIG = figure('/brand/screenshots/concierge-chat-window.webp', 380, 553,
    'Trendi Concierge chat window open on trendibizz.com, showing a greeting, a box to type a question, a microphone button, an optional recording checkbox and a notice that the visitor is chatting with an AI.',
    'The Concierge chat window on trendibizz.com, captured 15 November 2026.')
FORM_FIG = figure('/brand/screenshots/concierge-setup-request.webp', 450, 954,
    'The Concierge setup request form on trendibizz.com, with fields for business name, website and contact email, checkboxes for six channels and workflows, a plan choice and a notes box.',
    'The setup request form on <a href="/concierge-start">the setup page</a>, captured 15 November 2026. It prepares an email for you to send; nothing is charged or switched on by sending it.')

# ---------------- /ai-receptionist ----------------
def ai_receptionist(s):
    chat = ('<section class="design-section" id="chat-window"><div class="wrap"><p class="eyebrow">WHAT VISITORS SEE</p>'
      '<h2>The chat window, as it looks on this site</h2>' + CHAT_FIG +
      '<p>The window opens from a button in the corner of the page. It shows who the visitor is talking to, a greeting written for the business and a box to type a question. Two lines stay under the box in every conversation: an optional checkbox to record the conversation for the business, with audio kept for 30 days, and a plain notice that the visitor is chatting with an AI, that it can make mistakes, and that conversations may be saved so the team can follow up.</p>'
      '<p>That notice is there on purpose. Visitors should know they are not talking to a person, and you should be able to read what was said. Answers come from the pages and business information you approve. When the answer is not there, the assistant says so and offers to pass the question on instead of guessing.</p>'
      '<p>On this site the window also has a microphone button for a voice conversation in the browser. It only starts after the visitor allows microphone access, and if voice drops the visitor can keep typing. Visitors can ask for a copy of the conversation, and the window tells them when that copy is queued rather than claiming it has arrived.</p>'
      '</div></section>\n\n')
    s = once(s, '<section class="design-section" id="how">', chat + '<section class="design-section" id="how">', 'chat insert')

    old_how = re.search(r'<section class="design-section" id="how">.*?</section>', s, re.S).group(0)
    new_how = ('<section class="design-section" id="how"><div class="wrap"><p class="eyebrow">LESS SETUP. MORE SUPPORT.</p><h2>How setup works, step by step</h2><ol class="steps">'
      '<li><h3>Send a setup request</h3><p>Fill in the short form on the setup page: business name, website, a contact email, the channels you want and the plan. It prepares an email for you to review and send. Sending it does not create a subscription or switch anything on.</p></li>'
      '<li><h3>A person reads it and replies</h3><p>We check the request against your website and reply with what is realistic for the channels you picked, what it costs and what we need from you first.</p></li>'
      '<li><h3>You get a private portal</h3><p>An invitation lets you set your password and connect the accounts you approve. We never ask for the password to your website, your phone system or your inbox.</p></li>'
      '<li><h3>We load and test it</h3><p>We read your approved public pages into its knowledge, write down the rules (what it answers, what goes to a person, who to reach when something is urgent) and try the questions your customers ask.</p></li>'
      '<li><h3>You review, then it goes live</h3><p>You see the greeting, the handover rules and a set of real test conversations. One line of code adds the chat window, added by you or your developer, or we send you the snippet. Each additional channel is tested before activation.</p></li>'
      '</ol>' + FORM_FIG +
      '<p>Website chat usually goes live first, within days of your information being approved, because it needs no phone number and no carrier. Phone and SMS take longer: a provider in your country has to be connected and tested first. Anything that cannot be tested in your country is said out loud rather than switched on untested.</p>'
      '</div></section>')
    s = s.replace(old_how, new_how)

    needs = ('<section class="section--surface design-section" id="channel-needs"><div class="wrap"><p class="eyebrow">BEFORE GO-LIVE</p>'
      '<h2>What each channel needs before it goes live</h2><div class="grid3">'
      '<article class="card"><h3>Website chat</h3><p>Your approved pages and business information, and one script tag on your site. No phone number or carrier, which is why it is usually the first channel.</p></article>'
      '<article class="card"><h3>Email</h3><p>The mailbox you approve, connected in your portal. Customer email becomes a draft in your CRM, and replies are approved before anything is sent.</p></article>'
      '<article class="card"><h3>SMS</h3><p>A number and an SMS provider or carrier that operates in your country. Delivery depends on that provider, and its charges are billed by the provider.</p></article>'
      '<article class="card"><h3>Phone calls</h3><p>A business number and a voice provider. The number cannot be created for you, and what is available varies by country. Call recording and consent choices are yours; we will not pick them for you.</p></article>'
      '<article class="card"><h3>Bookings</h3><p>Your hours, the appointment length, the gaps between bookings and what should happen when nothing fits. You can subscribe to a private calendar feed; other calendar connections are agreed during setup.</p></article>'
      '<article class="card"><h3>Your existing CRM</h3><p>If you already use one, we agree how to connect it before you start and test it first. If you do not, Concierge keeps its own built-in CRM.</p></article>'
      '<article class="card"><h3>Social posts</h3><p>Your own business accounts, linked in your portal. Publishing is switched on per network after platform approval where required; X needs funded API access and TikTok needs Content Posting approval.</p></article>'
      '</div><p class="fine">Before any channel, we also need to know which enquiries a person must handle, the order of people to reach when something is urgent, and your retention and consent choices for stored messages.</p></div></section>\n\n'
      '<section class="design-section" id="limits"><div class="wrap"><p class="eyebrow">HONEST LIMITS</p><h2>What it does not do</h2><ul class="ticks">'
      '<li>It answers in English.</li>'
      '<li>It can make mistakes. That is why the notice sits under every conversation, why it is set up to admit a gap rather than guess, and why you can read every conversation.</li>'
      '<li>Phone, SMS and email work only once a provider is connected and tested. What is possible differs by country and provider.</li>'
      '<li>It does not take payments. Payment handoff or checkout has to be agreed and verified first; the current integration has not been certified to collect payments directly.</li>'
      '<li>Voicemail notices are planned, not live.</li>'
      '<li>It is the wrong buy if most of your enquiries are complex, bespoke or high value. A human answering service is likely the better fit, and we will tell you so.</li>'
      '<li>It does not promise leads, sales, bookings or rankings. It makes sure enquiries are answered and recorded instead of missed.</li>'
      '</ul><p>Concierge answers the enquiries that reach you. Helping more people find your site in the first place is a separate service, <a href="/seo">SEO and AI visibility</a>.</p></div></section>\n\n')
    s = once(s, '<section class="section--surface design-section" id="compare">', needs + '<section class="section--surface design-section" id="compare">', 'needs insert')

    s = once(s, '<p class="fine">Prices in USD. </p></div></section>',
      '<p class="fine">Prices in USD. </p><p class="fine">There is no per-call or per-minute charge from Trendi. Phone and SMS provider charges are separate and billed by that provider.</p></div></section>', 'price note')

    qas = [
      ('What do I need ready before setup?', 'Your website and the pages that may be used, your services, opening hours and service area, the answers to the questions customers ask most, which enquiries a person must handle, and appointment rules if you want bookings. For phone or SMS you also need a number and a provider in your country.'),
      ('How long does setup take?', 'Website chat usually goes live first, within days of your information being approved. Phone and SMS depend on connecting and testing a provider in your country, which takes longer.'),
      ('Do you need my website or inbox password?', 'No. Chat is added with one script tag by you or your developer, or we send the snippet. Account connections happen in your own portal with your permission.'),
    ]
    faq_anchor = re.search(r'(<section class="design-section" id="faq">.*?)(</div></section>)', s, re.S)
    s = s[:faq_anchor.end(1)] + faq_html(qas) + s[faq_anchor.end(1):]
    s = patch_jsonld(s, qas, 'ai-receptionist')
    s = once(s, '</ul></section></main>', '</ul>' + REVIEWED + '</section></main>', 'reviewed')
    typo = 'Prices are in USD;  We do not promise leads or sales.'
    n = s.count(typo)
    assert n in (0, 2), f'typo count {n}'
    s = s.replace(typo, 'Prices are in USD. We do not promise leads or sales.')
    return s

# ---------------- /ai-receptionist-cost ----------------
def cost(s):
    block = ('<section class="section--surface design-section" id="total-cost"><div class="wrap"><p class="eyebrow">YOUR OWN NUMBERS</p>'
      '<h2>How to work out your total cost</h2><ol class="steps">'
      '<li><h3>Start with the subscription</h3><p>Concierge is USD $250 a month with a 3-month minimum, then it renews monthly. The least you commit to is three months, USD $750.</p></li>'
      '<li><h3>Add provider charges for each channel</h3><p>Calls need a business number and a voice provider; texts need an SMS provider or carrier. Ask the provider in your country for its current rates. We do not quote them, because they vary by country and are billed by the provider, not by us.</p></li>'
      '<li><h3>Add anything else you want connected</h3><p>A paid CRM or calendar you already use, or email hosting if you do not have it yet.</p></li>'
      '<li><h3>Count your own time</h3><p>Setup needs your input: the pages it may use, your hours and service area, the questions customers ask, who handles what, and your appointment rules.</p></li>'
      '<li><h3>Compare it with what a missed enquiry costs you</h3><p>Not with a promised number of leads. We do not promise leads or sales; what the subscription pays for is enquiries answered and recorded instead of missed.</p></li>'
      '</ol></div></section>\n\n'
      '<section class="design-section" id="minimum-term"><div class="wrap"><p class="eyebrow">THE FIRST THREE MONTHS</p>'
      '<h2>What the minimum term pays for</h2>'
      '<p>The 3-month minimum is what pays for setup and testing, which happen before there is much to show. In that time a person checks your request against your website, your approved public pages are loaded into the assistant’s knowledge, the rules are written down, and each channel is tested before it is switched on. You see the greeting, the handover rules and a set of real test conversations before anything goes live.</p>'
      '<p>Website chat usually goes live first, within days of your information being approved, because it needs no number and no carrier. Phone and SMS take longer, since a provider in your country has to be connected and tested.</p>'
      + FORM_FIG +
      '</div></section>\n\n'
      '<section class="section--surface design-section" id="not-worth-it"><div class="wrap"><p class="eyebrow">WHEN IT IS NOT WORTH IT</p>'
      '<h2>When we would tell you not to buy it</h2><ul class="ticks">'
      '<li>Your enquiry volume is low enough that you already answer everything yourself. If the volume does not justify it, we will say so.</li>'
      '<li>Most of your enquiries are complex, bespoke or high value. A human answering service is likely the better buy.</li>'
      '<li>You need payments taken inside the conversation. The current integration has not been certified to collect payments directly.</li>'
      '<li>You need phone answering in a country where no provider can be connected and tested. We will say that before you commit, not after.</li>'
      '</ul><p>If the real problem is that too few people find your site, Concierge is not the fix. That is our separate <a href="/seo">SEO and AI visibility</a> service.</p></div></section>\n\n'
      '<section class="design-section" id="vendor-questions"><div class="wrap"><p class="eyebrow">COMPARING PRICES</p>'
      '<h2>Questions to ask any AI receptionist provider about price</h2><ol>'
      '<li><strong>What is the total cost at my volume?</strong> Subscription, plus per-minute or per-message provider charges, plus setup. Ask for a worked example at your own call and message volume.</li>'
      '<li><strong>Which charges come from someone else?</strong> Phone numbers, voice minutes and SMS are usually billed by a provider, not the software company.</li>'
      '<li><strong>What is the minimum term, and how do I leave?</strong> A three-month minimum is normal for a configured service; a lock-in with no exit is not.</li>'
      '<li><strong>Is setup and testing included, or billed separately?</strong></li>'
      '<li><strong>How do I get my data out?</strong> Export should not be a support ticket.</li>'
      '</ol><p>Our answers: USD $250 a month with a 3-month minimum, then monthly; provider charges billed by the provider; no separate Trendi setup fee listed; setup and channel testing are part of onboarding.</p></div></section>\n\n'
    )
    s = once(s, '<section class="design-section" id="price">', block + '<section class="design-section" id="price">', 'cost insert')
    qas = [
      ('What is the least I commit to?', 'Three months at USD $250 a month, USD $750 in total. After the minimum the plan renews monthly.'),
      ('Do provider charges go through Trendi?', 'No. Phone and SMS provider charges are separate and billed by that provider. There is no per-call or per-minute charge from Trendi.'),
      ('Can I start with website chat only?', 'Yes. Website chat needs no phone number or carrier, so it is usually the first channel to go live. Other channels can be added later, each tested before activation.'),
    ]
    faq_anchor = re.search(r'(<section class="design-section" id="faq">.*?)(</div></section>)', s, re.S)
    s = s[:faq_anchor.end(1)] + faq_html(qas) + REVIEWED + s[faq_anchor.end(1):]
    s = patch_jsonld(s, qas, 'cost')
    return s

# ---------------- /concierge-start ----------------
def start(s):
    block = ('<section class="design-section" id="first-channel"><div class="wrap"><h2>What goes on your site first</h2>' + CHAT_FIG +
      '<p>Most setups start with website chat, because it needs no phone number and no carrier. This is the window your visitors see, shown here as it runs on trendibizz.com. It opens from a button in the corner of the page, greets the visitor, and answers from the pages and business information you approved. When it does not know, it says so and offers to pass the question on.</p>'
      '<p>Every conversation carries a notice that the visitor is chatting with an AI, that it can make mistakes, and that conversations may be saved so your team can follow up. Recording is an opt-in checkbox, and audio is kept for 30 days. You read the conversations as they arrive, and the details a visitor leaves become an enquiry in the built-in CRM.</p>'
      '<p>The window is added with one script tag, by you or your developer, or we send you the snippet. Email, SMS and phone come after, each once its provider is connected and tested.</p>'
      '</div></section>\n')
    anchor = '<section class="design-section"><div class="wrap"><h2>Cost, term and what is not promised</h2>'
    if anchor not in s:
        i = s.find('Cost, term and what is not promised'); i = s.rfind('<section', 0, i); anchor = s[i:s.find('>', i)+1]
        s = s[:i] + block + s[i:]
    else:
        s = once(s, anchor, block + anchor, 'start insert')
    s = once(s, 'with a 3-month minimum</strong>; yearly billing is available after the first three months at USD $2,700.', 'with a 3-month minimum</strong>.', 'yearly clause')
    return s

PAGES = {'ai-receptionist.html': ai_receptionist, 'ai-receptionist-cost.html': cost, 'concierge-start.html': start}
for name, fn in PAGES.items():
    s = open(os.path.join(SRC, name)).read()
    out = fn(s)
    open(os.path.join(DST, name), 'w').write(out)
    print('built', name)
