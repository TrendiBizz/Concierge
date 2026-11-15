#!/usr/bin/env python3
"""Apply SEO Engine's 4 exact swaps (brief partners-referral-price-clarity-20261115.md) to live-base/ -> site/."""
import os
R = os.path.dirname(os.path.abspath(__file__))
SWAPS = {
 'partners.html': [
  ("Trendi costs USD $1,500 per month, with a three-month minimum",
   "Trendi's done-for-you SEO and AI visibility service costs USD $1,500 per month, with a three-month minimum", 1),
  ("Our price is USD $1,500 per month.",
   "The referral programme covers our SEO and AI visibility service, which is USD $1,500 per month.", 2),  # visible FAQ + FAQPage JSON-LD
  ("The first payment is the client's first USD $1,500 monthly invoice",
   "The first payment is the client's first USD $1,500 monthly invoice for SEO and AI visibility", 1),
 ],
 'terms.html': [
  ("That is the client's first USD $1,500 monthly invoice",
   "That is the client's first USD $1,500 monthly invoice for our SEO and AI visibility service", 1),
 ],
}
os.makedirs(os.path.join(R, 'site'), exist_ok=True)
for f, swaps in SWAPS.items():
    s = open(os.path.join(R, 'live-base', f), encoding='utf-8').read()
    for old, new, n in swaps:
        c = s.count(old)
        assert c == n, f'{f}: "{old}" found {c}x, expected {n}x - refusing to improvise'
        s = s.replace(old, new)
    open(os.path.join(R, 'site', f), 'w', encoding='utf-8').write(s)
    print('built', f)
