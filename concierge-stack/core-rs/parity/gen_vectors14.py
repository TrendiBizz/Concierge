"""Batch-14 golden vectors: the crawler (URL normalisation, link extraction, robots.txt, sitemaps and the crawl loop), taken from
the live modules (`app.crawler`, CPython's urllib.parse, html.parser and urllib.robotparser) with a fake network.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors14.py > ../concierge-stack/core-rs/parity/vectors14.json

No network is used. Article text extraction (trafilatura) is replaced by a deterministic fake on both sides.
"""
import asyncio
import json
import os
import random
import sys
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx

os.environ.setdefault("OUTBOX_ENABLED", "false")
sys.path.insert(0, os.getcwd())
from app import crawler, public_fetch  # noqa: E402

rng = random.Random(20261121)
out = {}


def run(coro):
    return asyncio.run(coro)


def outcome(fn):
    try:
        return {"ok": fn()}
    except ValueError:
        return {"err": "ValueError"}


# ---- URL handling ---------------------------------------------------------------------------------------------------------
schemes = ["http", "https", "HTTP", "ftp", "mailto", "javascript", "tel", "data", "", "file", "ws", "HtTpS"]
hosts = ["example.com", "www.example.com", "EXAMPLE.com", "sub.example.com", "example.com:8080", "user:pw@example.com", "[::1]", "[::1]:80", "1.2.3.4",
         "", "[v1.x]", "[vZ.x]", "[v.x]", "[v1.]", "[V1F.abc]", "[1.2.3.4]", "[zz]", "[::1", "::1]", "ex ample.com", "bücher.example", "exa\tmple.com", "www.", "WWW.Example.COM"]
paths = ["", "/", "/a", "/a/", "/a/b/c", "/a/./b", "/a/../b", "/../a", "/a//b", "/a;p=1", "/a;p=1/b;q=2", "/a.pdf", "/A.PDF", "/x.jpeg", "/img.PNG",
         "/page.html", "/a%20b", "/a b", "/é", "/a/b/..", "/a/b/.", "//evil.com/x", "/a?x=1", "a", "a/b", "../a", "./a", "..", ".", "/.xml", "/s.xml",
         "/a.json", "/a.JS", "/style.css", "/f.docx"]
queries = ["", "?x=1", "?x=1&y=2", "?", "?a=b#c"]
frags = ["", "#top", "#", "#a/b"]
relatives = ["", "#", "#x", "?q=1", "page", "/abs", "../up", "./same", "//other.com/p", "http://other.com/p", "https://www.example.com/p/", "mailto:a@b.co",
             "javascript:void(0)", "tel:+64211234567", " /pad ", "\t/tab", "/a\nb", "x/../../y", "/a;b", ";p", "?", "HTTP://UP.COM", "/a%2Fb", "g;x=1/./y"]
urls = {"norm": [], "join": [], "defrag": [], "host": []}
bases = ["https://example.com/", "https://example.com/dir/page", "http://www.example.com/a/b/c?x=1#f", "https://example.com", "https://example.com/dir/",
         "https://example.com/a;p/b", "", "ftp://example.com/x", "mailto:a@b.co", "https://user@example.com:8443/p"]
cases = set()
for _ in range(2600):
    s, h, p, q, f = rng.choice(schemes), rng.choice(hosts), rng.choice(paths), rng.choice(queries), rng.choice(frags)
    cases.add((s + "://" if s and rng.random() < 0.85 else (s + ":" if s else "")) + h + p + q + f if h or s else p + q + f)
cases.update(["", " ", "  https://example.com/x  ", "https://example.com/\t", "\x00https://example.com", "https://ex\nample.com/", "HTTPS://EXAMPLE.COM/A?B#C",
              "https://example.com:99999/", "https://example.com:abc/", "https://[::1]/", "https://[fe80::1%eth0]/", "https://[::ffff:1.2.3.4]/",
              "http:///x", "http:/x", "http:x", "//example.com/a", "///a", "https://exa%6Dple.com/", "https://ex@mple@host/", "https://@host/",
              "https://host:/p", "https://a.example/ünï", "https://ünï.example/"])
for u in sorted(cases):
    urls["norm"].append({"url": u, "base": None, "out": outcome(lambda u=u: crawler.normalize(u))})
    urls["host"].append({"url": u, "out": outcome(lambda u=u: crawler.host_of(u))})
    urls["defrag"].append({"url": u, "out": outcome(lambda u=u: urldefrag(u)[0])})
for _ in range(2600):
    b, r = rng.choice(bases), rng.choice(relatives)
    urls["join"].append({"base": b, "url": r, "out": outcome(lambda b=b, r=r: urljoin(b, r))})
    urls["norm"].append({"url": r, "base": b or None, "out": outcome(lambda b=b, r=r: crawler.normalize(r, b or None))})
out["urls"] = urls

# ---- HTML start tags and links --------------------------------------------------------------------------------------------------
class Rec(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append([tag, [[k, v] for k, v in attrs]])


def py_tags(html):
    p = Rec()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        return {"err": "exception"}
    return {"ok": p.tags}


frag_pool = [
    '<a href="/one">one</a>', "<A HREF='/Two'>two</A>", "<a href=/three>three</a>", '<a class="x" href="/four#f">four</a>', "<a href>none</a>", '<a href="">empty</a>',
    '<a href="https://other.com/x">ext</a>', '<a href="mailto:a@b.co">m</a>', '<a href="/file.pdf">pdf</a>', '<a href="/q?x=1&amp;y=2">q</a>',
    '<a href="/ent&#47;ity">n</a>', '<a href="/&copy;x">c</a>', '<a href="/&notit;">nn</a>', '<a href="/a&b=1">amp</a>', '<a href="/&#x2F;h">h</a>',
    '<a href="/&#0;z">z</a>', '<a href="/&#1;a">1</a>', '<a href="/&#x7f;b">2</a>', '<a href="/&#xfdd0;c">3</a>', '<a href="/&#xFFFE;d">4</a>', '<a href="/&#x1F;e">5</a>', '<a href="/&#x10FFFF;f">6</a>', '<a href="/&#x110000;g">7</a>', '<a href="/&#128;e">e</a>', '<a href="/&#xD800;s">s</a>', '<a href="/&#99999999999;l">l</a>', '<a href="/&amp=">eq</a>',
    "<a href=\"/one\" href='/dup'>dup</a>", "<a/>", '<a href="/self"/>', '<a href=/selfbare/>', "<a\nhref\n=\n'/nl'>", '<a href = "/sp" >', '<a href="/x"class="y">',
    '<a href=\'/mixed"quote\'>', '<a href=/a"b>', "<a title=x>no href</a>", '<a href="/unterminated', '<a href="/ok" <b>', "<a <b href=/inner>",
    "<p>text</p>", "<br/>", "<img src=/i.png>", "<div id=a><a href=/in-div>d</a></div>",
    "<!-- <a href=/commented> -->", "<!--> <a href=/after-abrupt>x</a>", "<!---> <a href=/after-abrupt2>y</a>", "<!-- c --!> <a href=/after-bang>z</a>",
    "<!-- unterminated <a href=/lost>", "<!DOCTYPE html>", "<!doctype html>", "<!DOCTYP html>", "<![CDATA[ <a href=/cdata> ]]>", "<![CDATA[ no end",
    "<?php echo '<a href=/pi>'; ?>", "<? unterminated", "<!bogus <a href=/b>", "<!bogus> <a href=/after-bogus>x</a>",
    "<script>var a = '<a href=/in-script>';</script>", "<SCRIPT>x</SCRIPT><a href=/after-script>s</a>", "<script>unterminated <a href=/lost2>",
    "<script/><a href=/not-cdata>nc</a>", "<style>a{}<a href=/in-style></style>", "<title>T <a href=/in-title></title>", "<TITLE>x</TITLE>",
    "<textarea><a href=/in-ta></textarea><a href=/after-ta>a</a>", "<xmp><a href=/xmp></xmp>", "<iframe><a href=/ifr></iframe>", "<noembed><a href=/ne></noembed>",
    "<plaintext><a href=/in-plain>", "<script>a</script >", "<script>a</scriptx><a href=/still>", "<script>a</script\t>", "</a>", "</ >", "</>", "</a", "</a b='>'>",
    "</ 1>", "< a href=/space>", "<", "<<a href=/dbl>", "a < b", "&amp; &lt; text", "&#x; &unknown;", "<a href=/trail", "<a href='/q'",
    '<a  \t href="/tabs"  >', "<a href=/semi;colon>", '<a href="/é">e</a>', '<a href="/%41">p</a>', '<a data-x=">" href=/after-gt>g</a>', "<a href='/it''s'>",
    "<A\x0chref=/ff>", "<a\x0bhref=/vt>", "<a href=/nul\x00x>", "<a href=\"/x\"\x00>", "<b a=1 a=2>", "<e1/2>", "<a  /  href=/slash>", "<a / href=/slash2>",
]
snips = []
for _ in range(1800):
    n = rng.randint(1, 7)
    snips.append("".join(rng.choice(frag_pool) + rng.choice(["", " ", "\n", "text"]) for _ in range(n)))
for fr in frag_pool:
    snips.append(fr)
    snips.append("<html><body>" + fr + "<a href=/end>end</a></body></html>")
snips += ["", " ", "no markup at all", "<a href=/x>" * 50]
html_cases = {"tags": [], "links": []}
for h in snips:
    html_cases["tags"].append({"html": h, "out": py_tags(h)})
    html_cases["links"].append({"html": h, "base": "https://example.com/dir/page", "out": outcome(lambda h=h: crawler.extract_links(h, "https://example.com/dir/page"))})
out["html"] = html_cases

# ---- robots.txt -----------------------------------------------------------------------------------------------------------------
UA = crawler.USER_AGENT
agents = ["*", "ConciergeBot", "conciergebot", "ConciergeBot/1.0", UA, "Concierge", "bot", "Googlebot", "", "CONCIERGEBOT", "concierge"]
rules_pool = ["/", "/private", "/private/", "/private/public", "/a*b", "/*.pdf$", "/*.pdf", "$", "/a$b", "/a$", "*", "**", "/x/*/y", "/x/*/y$", "/*?id=", "/search?q=*",
              "/p%61th", "/path", "/a b", "/é", "/%C3%A9", "", "/a**b", "/a$*", "/*", "/*/", "/a%2fb", "/a/b", "/tmp", "/tmp/", "/robots.txt", "/?", "/a?b=c&d=e"]
paths_to_test = ["/", "/private", "/private/x", "/private/public", "/path", "/pa th", "/page.pdf", "/a/page.pdf", "/aXb", "/ab", "/x/1/y", "/x/1/y/z", "/x/y",
                 "/search?q=hello", "/search", "/list?id=5", "/robots.txt", "/é", "/%C3%A9", "/tmp/file", "/tmp", "/a/b", "/a%2Fb", "/?", "/a?b=c&d=e", "/p%61th",
                 "/a$b", "/AB", "/private%2Fx", "", "/a;x"]
robots = []
for _ in range(500):
    lines = []
    for _g in range(rng.randint(1, 3)):
        for _a in range(rng.randint(1, 2)):
            lines.append(rng.choice(["User-agent", "user-agent", "USER-AGENT", "User-Agent ", "useragent"]) + rng.choice([": ", ":", " : "]) + rng.choice(agents))
        for _r in range(rng.randint(0, 4)):
            lines.append(rng.choice(["Disallow", "Allow", "disallow", "ALLOW", "Crawl-delay", "Request-rate", "Sitemap", "Noindex"]) + ": " + rng.choice(rules_pool + ["10", "1/5", "http://x/sitemap.xml"])
                         + rng.choice(["", " # comment", "  "]))
        if rng.random() < 0.6:
            lines.append(rng.choice(["", "# only a comment", "   "]))
    if rng.random() < 0.15:
        lines.insert(0, "Disallow: /early")
    text = rng.choice(["\n", "\r\n", "\r", "\x0b"]) .join(lines)
    checks = []
    from urllib.robotparser import RobotFileParser
    other = RobotFileParser()
    other.parse(text.splitlines())
    ours = crawler.Robots(text)
    for p in rng.sample(paths_to_test, 12):
        url = "https://example.com" + p
        checks.append({"ua": UA, "url": url, "allowed": ours.allowed(url)})
        if rng.random() < 0.4:
            checks.append({"ua": "OtherBot/2.0", "url": url, "allowed": other.can_fetch("OtherBot/2.0", url)})
        if rng.random() < 0.2:
            checks.append({"ua": "conciergebot", "url": url, "allowed": other.can_fetch("conciergebot", url)})
        if rng.random() < 0.3:
            checks.append({"ua": "bot*/1.0", "url": url, "allowed": other.can_fetch("bot*/1.0", url)})
    robots.append({"text": text, "checks": checks})
robots.append({"text": "User-agent: *\nDisallow: /a\n\nUser-agent: x\nAllow: /a\n", "checks": [
    {"ua": "x*y", "url": "https://example.com/a", "allowed": (lambda r: (r.parse("User-agent: *\nDisallow: /a\n\nUser-agent: x\nAllow: /a\n".splitlines()), r.can_fetch("x*y", "https://example.com/a"))[1])(__import__("urllib.robotparser", fromlist=["x"]).RobotFileParser())}]})
robots.append({"text": "", "checks": [{"ua": UA, "url": "https://example.com/x", "allowed": crawler.Robots("").allowed("https://example.com/x")}]})
out["robots"] = robots

# normalisation helpers used by robots
from urllib import robotparser as rp_mod  # noqa: E402

samples = ["", "/", "/a b", "/a%20b", "/%", "/%4", "/%zz", "/%41%42", "/é", "/%C3%A9", "/%E9", "/%ff", "/a?b=c&d=%7E", "/a?x=a b&y", "/a%3Fb?c", "/~user", "/a_b-c.d",
           "/a+b", "/a,b;c", "/a#b", "/ü?ü=ü", "/%2F", "/a/../b", "/%25", "/a?%3D=%26", "/ ", "/😀"]
out["quote"] = [{"in": s, "norm": rp_mod.normalize(s), "uri": rp_mod.normalize_uri(s)} for s in samples]

# ---- sitemaps ---------------------------------------------------------------------------------------------------------------------
class Resp:
    def __init__(self, status=200, text="", ctype="text/html", size=None):
        self.status_code = status
        self.text = text
        self.headers = {"content-type": ctype}

        class C:
            def __len__(_):
                return size if size is not None else len(text.encode())

        self.content = C()


class FakeClient:
    def __init__(self, spec):
        self.spec = spec
        self.log = []

    async def get(self, url):
        self.log.append(url)
        r = self.spec.get(url)
        if r is None or r == "fail":
            raise httpx.ConnectError("down")
        return Resp(r.get("status", 200), r.get("text", ""), r.get("ctype", "text/html"), r.get("size"))


def locs(urls_):
    return "".join(rng.choice(["<loc>%s</loc>", "<loc> %s </loc>", "<LOC>%s</LOC>", "<loc>\n%s\n</loc>", "<url><loc>%s</loc></url>"]) % u for u in urls_)


sm = []
base = "https://example.com/"
for _ in range(150):
    spec = {}
    cand = ["https://example.com/", "https://example.com/a", "https://www.example.com/b", "https://other.com/c", "https://example.com/d.pdf", "https://example.com/e?x=1&amp;y=2",
            "ftp://example.com/f", "https://example.com/g#frag", "  https://example.com/h  ", "https://example.com/i/", "https://example.com/sub.XML", "https://example.com/k"]
    main = locs(rng.sample(cand, rng.randint(0, 8)))
    if rng.random() < 0.4:
        main += locs(["https://example.com/n%d.xml" % i for i in range(rng.randint(1, 8))])
    spec["https://example.com/sitemap.xml"] = rng.choice([{"text": main}, {"text": main}, {"text": main, "status": 404}, "fail", {"text": ""}])
    for i in range(8):
        spec["https://example.com/n%d.xml" % i] = rng.choice([{"text": locs(rng.sample(cand, rng.randint(0, 5)))}, {"text": locs(["https://example.com/n%d.xml" % ((i + 1) % 8)] + cand[:2])},
                                                              "fail", {"status": 500}])
    spec["https://example.com/sub.XML"] = {"text": locs(cand[:3])}
    limit = rng.choice([1, 3, 6, 120])
    fc = FakeClient(spec)
    try:
        res = {"ok": run(crawler._sitemap_urls(fc, base, limit))}
    except ValueError:
        res = {"err": "ValueError"}
    sm.append({"spec": spec, "limit": limit, "out": res, "log": fc.log})
out["sitemap"] = sm

# ---- fetch rules ------------------------------------------------------------------------------------------------------------------
fetches = []
for status in (200, 201, 204, 301, 404, 500):
    for ctype in ("text/html", "TEXT/HTML; charset=utf-8", "application/xhtml+xml", "application/json", "", "text/plain", "html"):
        for size in (0, 100, 3_000_000, 3_000_001):
            fc = FakeClient({"https://e.com/p": {"status": status, "ctype": ctype, "text": "BODY", "size": size}})
            fetches.append({"status": status, "ctype": ctype, "size": size, "out": run(crawler._fetch(fc, "https://e.com/p"))})
fetches.append({"status": "fail", "ctype": "", "size": 0, "out": run(crawler._fetch(FakeClient({}), "https://e.com/p"))})
out["fetch"] = fetches

# ---- the crawl loop ---------------------------------------------------------------------------------------------------------------
def fake_extract(url, html):
    if "noextract" in html:
        return None
    return crawler.Page(url=url, title="T%d" % (len(html) % 7), text=html[:30])


class FakeTransport:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *e):
        return False


async def no_sleep(_):
    return None


crawler.extract_page = fake_extract
crawler.httpx.AsyncClient = FakeTransport
asyncio.sleep_orig = asyncio.sleep
site_urls = ["https://example.com/"] + ["https://example.com/" + p for p in
                                         ["a", "b", "c/d", "c/e", "f.pdf", "g", "h/", "i?x=1", "j#top", "private/k", "private/public/l", "m", "n", "o", "p", "q"]]
crawls = []
for case in range(160):
    spec = {}
    pages_ = rng.sample(site_urls[1:], rng.randint(3, 14))
    for u in [site_urls[0]] + pages_:
        links = []
        for _ in range(rng.randint(0, 7)):
            t = rng.choice(site_urls + ["/rel", "a", "../b", "https://www.example.com/g", "http://example.com/a", "https://other.com/x", "mailto:x@y.z", "#frag", "/private/z",
                                        "https://example.com:8080/a", "//example.com/b"])
            links.append('<a href="%s">l</a>' % t)
        body = "".join(links) + rng.choice(["", " noextract", " plenty of readable text " * 4])
        spec[u] = rng.choice([{"text": body}] * 14 + [{"text": body, "status": 404}, {"text": body, "ctype": "application/json"}, "fail", {"text": body, "size": 4_000_000}])
        if u == site_urls[0] and rng.random() < 0.8:
            spec[u] = {"text": body + ' <a href="/a">x</a><a href="/b">y</a><a href="/c/d">z</a>'}
    if rng.random() < 0.7:
        spec["https://example.com/robots.txt"] = rng.choice([{"text": "User-agent: *\nDisallow: /private\n"}, {"text": "User-agent: ConciergeBot\nDisallow: /private\nAllow: /a$\n"}, {"text": "User-agent: conciergebot\nDisallow: /\nAllow: /a$\n"},
                                                            {"text": "User-agent: *\nDisallow: /*.pdf$\nAllow: /private/public\nDisallow: /private\n"}, {"status": 404},
                                                            {"status": 403, "text": "User-agent: *\nDisallow: /"}, "fail", {"text": ""}])
    if rng.random() < 0.6:
        spec["https://example.com/sitemap.xml"] = {"text": locs(rng.sample(site_urls, rng.randint(1, 9)) + (["https://other.com/off"] if rng.random() < 0.3 else []))}
    start = rng.choice(["https://example.com/"] * 5 + ["https://example.com", "https://www.example.com/", "http://EXAMPLE.com/#x", "https://example.com/a", "https://example.com/a", "ftp://example.com/", "notaurl", "https://example.com/a.pdf"])
    max_pages = rng.choice([1, 2, 3, 5, 40])
    conc = rng.choice([4, 4, 4, 1, 2, 3])
    fc = FakeClient(spec)
    public_fetch.PublicClient = lambda transport, host, fc=fc: fc
    asyncio.sleep = no_sleep
    try:
        res = run(crawler.crawl(start, max_pages=max_pages, concurrency=conc))
        o = {"ok": [[p.url, p.title, p.text] for p in res]}
    except ValueError:
        o = {"err": "ValueError"}
    asyncio.sleep = asyncio.sleep_orig
    crawls.append({"spec": spec, "start": start, "max_pages": max_pages, "concurrency": conc, "out": o, "log": fc.log})
for n_links, max_pages in [(8, 1), (9, 1), (10, 1), (18, 2), (19, 2), (20, 2)]:
    spec = {"https://example.com/": {"text": "noextract " + "".join('<a href="/p%d">x</a>' % i for i in range(1, n_links + 1))}}
    for i in range(1, n_links + 1):
        spec["https://example.com/p%d" % i] = {"text": 'noextract <a href="/z%d">z</a>' % i}
        spec["https://example.com/z%d" % i] = {"text": "noextract"}
    fc = FakeClient(spec)
    public_fetch.PublicClient = lambda transport, host, fc=fc: fc
    asyncio.sleep = no_sleep
    res = run(crawler.crawl("https://example.com/", max_pages=max_pages, concurrency=4))
    asyncio.sleep = asyncio.sleep_orig
    crawls.append({"spec": spec, "start": "https://example.com/", "max_pages": max_pages, "concurrency": 4, "out": {"ok": [[p.url, p.title, p.text] for p in res]}, "log": fc.log})
out["crawl"] = crawls

json.dump(out, sys.stdout, ensure_ascii=True, separators=(",", ":"))
