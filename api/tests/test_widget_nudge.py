"""H4: proactive chat nudge is opt-in, path-scoped, once per session, and CSP safe."""
import pathlib
import shutil
import subprocess
import textwrap

import pytest

WIDGET = pathlib.Path(__file__).resolve().parents[1] / "static" / "widget.js"


def test_nudge_is_opt_in_and_bounded():
    src = WIDGET.read_text()
    assert 'getAttribute("data-nudge-seconds") || "0"' in src  # default off
    assert "Math.min(600" in src
    assert "NUDGE_SECONDS > 0 && !AUTOOPEN" in src
    assert 'sessionStorage.setItem(NUDGE_KEY, "1")' in src  # once per session
    assert "nudgeText" in src and "textContent" not in src.split("var nudgeText")[1][:200]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_path_matching_logic():
    src = WIDGET.read_text()
    start = src.index("var NUDGE_PATHS")
    end = src.index("// ---", start)
    snippet = src[start:end]
    js = textwrap.dedent("""
        var script = {getAttribute: function (n) { return n === "x" ? "" : "/pricing, /quote/"; }};
        %s
        var out = [nudgeAppliesToPath("/pricing"), nudgeAppliesToPath("/pricing/x"),
                   nudgeAppliesToPath("/pricingx"), nudgeAppliesToPath("/quote"), nudgeAppliesToPath("/")];
        console.log(JSON.stringify(out));
    """) % snippet.replace('script.getAttribute("data-nudge-paths") || ""', 'script.getAttribute("p")')
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "[true,true,false,true,false]"
