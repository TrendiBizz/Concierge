"""website/ui/trendi-ui.js: vanilla ports of Sonner, Vaul, cmdk, NumberFlow and Beautiful UI ideas.

Checks the behaviour rules taken from each library (run in node), the site rules the file must keep
(CSP-safe, no innerHTML, reduced motion, licence credit) and that the Cmd-K search index is fresh.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
UI = ROOT / "website" / "ui"
JS = UI / "trendi-ui.js"
CSS = UI / "trendi-ui.css"
INDEX = UI / "search-index.json"
needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


def run_node(body: str):
    js = "const L = require(%s)._logic;\n%s" % (json.dumps(str(JS)), body)
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@needs_node
def test_command_score_ranks_like_cmdk():
    out = run_node("""
      const items = [{label: 'Pen testing'}, {label: 'Pricing'}, {label: 'Privacy policy'}, {label: 'About'}];
      console.log(JSON.stringify({
        pr: L.rankItems(items, 'pri').map(i => i.label),
        none: L.rankItems(items, 'zzz').length,
        empty: L.rankItems(items, '').map(i => i.label),
        exact: L.commandScore('Pricing', 'Pricing') > L.commandScore('Pricing plans', 'Pricing'),
        alias: L.rankItems([{label: 'Concierge', keywords: ['receptionist']}], 'recept').length,
        // Equal cmdk scores: the label where the text appears earliest wins (found in the 2026-11-27 smoke run).
        tie: L.rankItems([{label: 'AI receptionist cost: AI office pricing'}, {label: 'Concierge pricing: from USD $199'}], 'pric')[0].label,
      }));
    """)
    assert out["pr"][0] == "Pricing" and "About" not in out["pr"]
    assert out["none"] == 0
    assert out["empty"] == ["Pen testing", "Pricing", "Privacy policy", "About"]  # empty query keeps order
    assert out["exact"] is True
    assert out["alias"] == 1  # keywords from the meta description are searchable
    assert out["tie"].startswith("Concierge pricing")


@needs_node
def test_sheet_release_follows_vaul_thresholds():
    out = run_node("""
      console.log(JSON.stringify([
        L.sheetRelease(-50, 400, 2),   // upward: never closes
        L.sheetRelease(20, 400, 0.5),  // fast flick down
        L.sheetRelease(100, 400, 0.1), // exactly 25% of height
        L.sheetRelease(99, 400, 0.1),  // just under 25%, slow
      ]));
    """)
    assert out == ["reset", "close", "close", "reset"]


@needs_node
def test_toast_stack_and_swipe_follow_sonner():
    out = run_node("""
      const hs = [50, 60, 70, 80];
      console.log(JSON.stringify({
        collapsed: [0,1,2,3].map(i => L.toastLayout(i, hs, false)),
        expanded: [0,1,2].map(i => L.toastLayout(i, hs, true).y),
        swipe: [L.toastDismissed(45, 0), L.toastDismissed(-44, 0), L.toastDismissed(10, 0.2)],
      }));
    """)
    c = out["collapsed"]
    assert [x["hidden"] for x in c] == [False, False, False, True]  # three visible
    assert c[0]["scale"] == 1 and c[1]["scale"] < 1 and c[1]["y"] < 0  # older ones peek behind, smaller
    assert out["expanded"] == [0, -64, -138]  # hover fans out: heights + 14px gap
    assert out["swipe"] == [True, False, True]


@needs_node
def test_ticker_rolls_digits_and_keeps_symbols():
    out = run_node("console.log(JSON.stringify(L.tickerParts('NZ$1,204.50')))")
    digits = [p["value"] for p in out if p["digit"]]
    symbols = "".join(p["value"] for p in out if not p["digit"])
    assert digits == [1, 2, 0, 4, 5, 0]
    assert symbols == "NZ$,."


def test_file_keeps_site_rules():
    src = JS.read_text()
    assert "innerHTML" not in src  # every string goes in via textContent / text nodes
    assert 'setAttribute("style"' not in src and "cssText" not in src  # CSP style-src 'self'
    assert not re.search(r"h\(\"style\"|createElement\(\"style\"", src)  # no injected <style> element
    assert src.count("reducedMotion()") >= 4
    assert "dlg.setPointerCapture" in src  # sheet release must arrive when the drag ends off the sheet
    for credit in ("Sonner (MIT", "Vaul (MIT", "cmdk (MIT", "NumberFlow (MIT", "Beautiful UI (MIT", "Paco Coursey"):
        assert credit in src
    css = CSS.read_text()
    assert "prefers-reduced-motion: reduce" in css
    assert not re.search(r"font-family:(?!\s*var\(--font)", css), "type must come from the brand --font token"
    assert "var(--accent" in css


def test_search_index_is_fresh_and_only_lists_sitemap_pages():
    res = subprocess.run([sys.executable, str(ROOT / "scripts/seo/build_search_index.py"), "--check"],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    pages = json.loads(INDEX.read_text())["pages"]
    sitemap = (ROOT / "website/sitemap.xml").read_text()
    assert len(pages) > 20
    for p in pages:
        assert p["label"] and "| Trendi" not in p["label"]
        url = "https://trendibizz.com" + ("" if p["href"] == "/" else p["href"])
        assert f"<loc>{url}{'/' if p['href'] == '/' else ''}</loc>" in sitemap


def test_site_pages_and_scripts_wire_trendi_ui():
    web = ROOT / "website"
    html_files = sorted(web.rglob("*.html"))
    assert len(html_files) >= 50
    for p in html_files:
        text = p.read_text(encoding="utf-8")
        assert "/ui/trendi-ui.css" in text, f"missing trendi-ui.css in {p}"
        assert "/ui/trendi-ui.js" in text, f"missing trendi-ui.js in {p}"
        assert text.index("/ui/trendi-ui.js") < text.index("main.js"), f"trendi-ui.js must precede main.js in {p}"

    main_js = (web / "main.js").read_text(encoding="utf-8")
    for token in ("TrendiUI.sheet", "TrendiUI.commandMenu", "TrendiUI.toast", "TrendiUI.ticker", 'aria-busy="true"'):
        assert token in main_js, f"missing {token} in main.js"

    calc_js = (web / "tools/missed-call-cost-calculator.js").read_text(encoding="utf-8")
    assert "TrendiUI.ticker" in calc_js and "TrendiUI.toast" in calc_js

    for tool in ("tools/site-check.js", "tools/robots-ai-check.js"):
        src = (web / tool).read_text(encoding="utf-8")
        assert "TrendiUI.aiStatus" in src, f"missing TrendiUI.aiStatus in {tool}"


def test_studio_uses_real_ui_libraries_with_brand_restyle():
    portal = ROOT / "web" / "portal"
    pkg = json.loads((portal / "package.json").read_text(encoding="utf-8"))
    deps = pkg.get("dependencies", {})
    for lib in ("sonner", "cmdk", "@number-flow/react", "vaul"):
        assert lib in deps, f"missing {lib} in web/portal/package.json"

    assert "from 'sonner'" in (portal / "src/Notify.tsx").read_text(encoding="utf-8")
    assert "from 'cmdk'" in (portal / "src/CmdK.tsx").read_text(encoding="utf-8")
    assert "from 'vaul'" in (portal / "src/TabGuideDrawer.tsx").read_text(encoding="utf-8")
    for f in ("src/Home.tsx", "src/Pipeline.tsx", "src/Quotes.tsx"):
        assert "from '@number-flow/react'" in (portal / f).read_text(encoding="utf-8")

    css = (portal / "src/shell.css").read_text(encoding="utf-8")
    assert "Plus Jakarta Sans" in css and "#7c5cff" in css
    assert "prefers-reduced-motion: reduce" in css
    assert (portal / "public/fonts/plus-jakarta-sans-var.woff2").exists()
    # dist/ is a gitignored build artifact (CI never builds it), so assert what the repo holds:
    # the build entry and the script that produces dist. verify-deploy.sh proves the built copy.
    assert (portal / "index.html").exists() and "build" in pkg.get("scripts", {})
