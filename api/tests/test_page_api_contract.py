"""Every /api/ path a website page calls must be served by FastAPI AND routed to it by Caddy.

Why (2026-11-24): the AI-robots checker called GET /api/robots, the worker that served it was removed in the VPS
cutover, and the endpoint answered 404 for days with every test green. scripts/verify/check_page_api_contract.py
scans website/**/*.js and *.html; this file runs it in the suite (scripts/seo-gate.sh runs it too) and proves it
FAILS on a deliberately broken tree, so the guard cannot rot into something that always passes.
"""
import importlib.util
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify" / "check_page_api_contract.py"
_spec = importlib.util.spec_from_file_location("page_api_contract", SCRIPT)
contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contract)

CALLED = {"/api/enquiry", "/api/robots", "/api/security-check", "/api/site-check"}


def clone(tmp_path: pathlib.Path) -> pathlib.Path:
    """A minimal copy of the three inputs the scan reads, safe to break."""
    for rel in ("website/tools", "api/app/routers", "scripts/vps"):
        shutil.copytree(ROOT / rel, tmp_path / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "._*"))
    for js in ("website/main.js", "website/concierge-start.js"):
        shutil.copy(ROOT / js, tmp_path / js)
    return tmp_path


def test_the_real_tree_passes_and_finds_every_endpoint_the_pages_call():
    assert set(contract.page_calls(ROOT)) >= CALLED
    assert contract.check(ROOT) == []


def test_it_runs_as_a_script_and_exits_zero():
    done = subprocess.run([sys.executable, "-I", str(SCRIPT), str(ROOT)], capture_output=True, text=True)
    assert done.returncode == 0 and "PAGE API CONTRACT: OK" in done.stdout


def test_paths_mode_lists_the_called_endpoints_for_the_drift_guard():
    done = subprocess.run([sys.executable, "-I", str(SCRIPT), str(ROOT), "--paths"], capture_output=True, text=True)
    assert CALLED <= set(done.stdout.split())


def test_a_page_calling_an_endpoint_nothing_serves_fails(tmp_path):
    root = clone(tmp_path)
    page = root / "website" / "tools" / "new-tool.js"
    page.write_text('fetch("/api/brand-new-tool", {method: "POST"});\n')
    problems = contract.check(root)
    assert any("/api/brand-new-tool" in p and "no FastAPI route" in p for p in problems)
    assert any("/api/brand-new-tool" in p and "no Caddy handler" in p for p in problems)
    done = subprocess.run([sys.executable, "-I", str(SCRIPT), str(root)], capture_output=True, text=True)
    assert done.returncode == 1 and "PAGE API CONTRACT: FAIL" in done.stdout


@pytest.mark.parametrize("path", ["/api/robots", "/api/site-check", "/api/security-check"])
def test_a_missing_fastapi_route_fails(tmp_path, path):
    root = clone(tmp_path)
    public = root / "api" / "app" / "routers" / "public.py"
    public.write_text(public.read_text().replace(f'("{path}"', '("/api/renamed-away"'))
    problems = contract.check(root)
    assert any(path in p and "no FastAPI route" in p for p in problems), problems


@pytest.mark.parametrize("path", ["/api/robots", "/api/site-check", "/api/security-check", "/api/enquiry"])
def test_a_missing_caddy_route_fails(tmp_path, path):
    root = clone(tmp_path)
    caddy = root / "scripts" / "vps" / "Caddyfile"
    text = caddy.read_text()
    assert path in text
    caddy.write_text(text.replace(path, "/api/never-called"))
    problems = contract.check(root)
    assert any(path in p and "no Caddy handler" in p for p in problems), problems


def test_a_caddy_route_that_goes_to_the_website_instead_of_the_api_fails(tmp_path):
    root = clone(tmp_path)
    caddy = root / "scripts" / "vps" / "Caddyfile"
    text = caddy.read_text()
    block = text[text.index("handle @tools {"):text.index("@website host")]
    caddy.write_text(text.replace(block, block.replace("reverse_proxy api:8000", "reverse_proxy website:8080")))
    assert any("/api/site-check" in p and "no Caddy handler" in p for p in contract.check(root))


def test_the_gate_script_runs_the_contract_check():
    gate = (ROOT / "scripts" / "seo-gate.sh").read_text()
    assert "check_page_api_contract.py" in gate and "page API contract" in gate


def test_the_route_must_serve_the_method_the_page_uses(tmp_path):
    """A GET-only (or OPTIONS-only) route must not satisfy a page that POSTs to it."""
    root = clone(tmp_path)
    public = root / "api" / "app" / "routers" / "public.py"
    public.write_text(public.read_text().replace('@router.post("/api/security-check"', '@router.post("/api/security-check-RENAMED"'))
    problems = contract.check(root)
    assert any("/api/security-check" in p and "no FastAPI route serves POST" in p for p in problems), problems
    assert contract.page_calls(ROOT)["/api/security-check"]["methods"] == {"POST"}
    assert contract.page_calls(ROOT)["/api/robots"]["methods"] == {"GET"}
