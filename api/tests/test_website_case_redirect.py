"""/Concierge (capital C) must 301 to /concierge. Runs the real scripts/vps/website.mjs against a temp site."""
import pathlib
import shutil
import socket
import subprocess
import time
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
NODE = shutil.which("node")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _get(port, path):
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        r = opener.open(f"http://127.0.0.1:{port}{path}", timeout=5)
        return r.status, r.headers.get("Location")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location")


def _ctype(port, path):
    r = urllib.request.build_opener(_NoRedirect).open(f"http://127.0.0.1:{port}{path}", timeout=5)
    return r.headers.get("Content-Type")


@pytest.fixture()
def server(tmp_path):
    if not NODE:
        pytest.skip("node not installed")
    site = tmp_path / "website" / "site"
    site.mkdir(parents=True)
    (tmp_path / "website" / "deploy_known_good").mkdir()
    (tmp_path / "website" / "deploy_known_good" / "_worker.js").write_text("export default {fetch(req,env){return env.ASSETS.fetch(req)}}")
    (site / "_headers").write_text("")
    (site / "_redirects").write_text("")
    (site / "index.html").write_text("home")
    (site / "concierge.html").write_text("concierge")
    (site / "404.html").write_text("nope")
    (site / "Logo.png").write_text("png")
    (site / "cap.vtt").write_text("WEBVTT\n")
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    src = (ROOT / "scripts/vps/website.mjs").read_text()
    src = src.replace("'/website/", f"'{tmp_path}/website/").replace("root = '/website/site'", f"root = '{site}'").replace(".listen(8080,", f".listen({port},")
    (tmp_path / "w.mjs").write_text(src)
    proc = subprocess.Popen([NODE, str(tmp_path / "w.mjs")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            _get(port, "/"); break
        except Exception:
            time.sleep(0.1)
    yield port
    proc.terminate()


def test_capital_path_redirects_to_lowercase(server):
    assert _get(server, "/Concierge") == (301, "/concierge")
    assert _get(server, "/CONCIERGE?x=1") == (301, "/concierge?x=1")
    assert _get(server, "/Concierge/") == (301, "/concierge")


def test_lowercase_and_unknown_and_real_capital_files(server):
    assert _get(server, "/concierge")[0] == 200
    assert _get(server, "/Nopage")[0] == 404
    assert _get(server, "/Logo.png")[0] == 200


def test_caption_files_are_served_as_text_vtt(server):
    assert _ctype(server, "/cap.vtt").startswith("text/vtt")
