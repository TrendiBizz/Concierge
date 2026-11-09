"""Batch-8 golden vectors: SSRF guard (ipaddress.is_global and the same-site HTTPS URL rule), run through live stdlib.

    python3 concierge-stack/core-rs/parity/gen_vectors8.py > concierge-stack/core-rs/parity/vectors8.json
The URL rule mirrors the inline condition at the top of PublicClient.get (public_fetch.py), using the live urlsplit.
"""
import ipaddress
import json
import random
import sys
from urllib.parse import urlsplit

rng = random.Random(20261116)
c4, c6 = ipaddress._IPv4Constants, ipaddress._IPv6Constants

addrs = set()
for net in list(c4._private_networks) + list(c4._private_networks_exceptions) + [c4._public_network]:
    first, last = int(net.network_address), int(net.broadcast_address)
    for v in (first - 1, first, first + 1, last - 1, last, last + 1):
        if 0 <= v < 2**32:
            addrs.add(str(ipaddress.IPv4Address(v)))
for net in list(c6._private_networks) + list(c6._private_networks_exceptions):
    first, last = int(net.network_address), int(net.broadcast_address)
    for v in (first - 1, first, first + 1, last - 1, last, last + 1):
        if 0 <= v < 2**128:
            addrs.add(str(ipaddress.IPv6Address(v)))
for _ in range(400):
    addrs.add(str(ipaddress.IPv4Address(rng.getrandbits(32))))
for _ in range(300):
    addrs.add(str(ipaddress.IPv6Address(rng.getrandbits(128))))
for a in list(addrs):
    if "." in a and ":" not in a:  # IPv4-mapped IPv6 of each pure v4 address
        addrs.add("::ffff:" + a)
        addrs.add(str(ipaddress.IPv6Address(int(ipaddress.IPv4Address(a)) | (0xFFFF << 32))))
addrs |= {"8.8.8.8", "1.1.1.1", "2606:4700:4700::1111", "2001:4860:4860::8888", "::", "::1", "fe80::1%eth0", "010.0.0.1", "1.2.3", "1.2.3.4.5", "", "localhost",
          "999.1.1.1", "::ffff:127.0.0.1", "::ffff:8.8.8.8", "0.0.0.0", "255.255.255.255", "100.64.0.1", "169.254.169.254", "metadata.google.internal"}
ip_cases = []
for a in sorted(addrs):
    try:
        ip_cases.append({"ip": a, "out": ipaddress.ip_address(a).is_global})
    except ValueError:
        ip_cases.append({"ip": a, "out": None})

URLS = ["https://example.com/", "https://www.example.com/x", "https://EXAMPLE.com", "http://example.com", "HTTPS://example.com", "https://example.com:443/", "https://example.com:8443/",
        "https://example.com:/", "https://example.com:abc/", "https://example.com:99999/", "https://example.com:0443/", "https://user@example.com/", "https://user:pw@example.com/",
        "https://:@example.com/", "https://@example.com/", "https://example.com@evil.com/", "https://evil.com#@example.com/", "https://evil.com\\@example.com/", "//example.com/x",
        "https:example.com", "  https://example.com", "https://exa\tmple.com", "https://[::1]/", "https://[::1", "https://example.com]", "https://[example.com]/", "https:///path", "https://",
        "", "ftp://example.com", "https://sub.example.com", "https://example.com.evil.com", "https://www.www.example.com", "https://xn--example-9d0b.com", "https://exämple.com",
        "https://example.com%2f@evil.com", "https://127.0.0.1/", "https://example.com?x=1", "https://example.com#frag", "https://example.com/a/b?c=d#e", "https://www.example.com:443/robots.txt",
        "https://example.com:443:80/", "https://example.com:-1/", "https://example.com: 443/", "https://example.com:４４３/", "https:\\\\example.com", "https://example.com\n.evil.com",
        "javascript://example.com/%0aalert(1)", "https://user:@example.com/", "https://:pw@example.com/", "https://a@b@example.com/", "https://example.com:65535/", "https://example.com:65536/"]
url_cases = []
for host in ("example.com", "www.example.com", "EXAMPLE.COM"):
    for url in URLS:
        site = host.lower().removeprefix("www.")
        try:
            parts = urlsplit(url)
            bad = (parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443)
                   or parts.hostname.lower().removeprefix("www.") != site)
            out = "not_same_site" if bad else "allowed"
        except ValueError:
            out = "unparseable"
        url_cases.append({"url": url, "host": host, "out": out})

print(json.dumps({"ip": ip_cases, "urls": url_cases, "python": sys.version.split()[0]}, ensure_ascii=False, indent=0))
