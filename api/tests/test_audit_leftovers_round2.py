"""Regression tests for Round 2 Item 12 (Audit Leftovers)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_healthcheck():
    spec = importlib.util.spec_from_file_location("hc_mod", REPO_ROOT / "scripts/vps/healthcheck.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_healthcheck_deploying_does_not_hide_crash_loops(monkeypatch):
    hc = _load_healthcheck()
    monkeypatch.setattr(hc, "recently_started", lambda name, minutes=10: True)
    # Crash-looping container (RestartCount > 0) must NOT be treated as deploying
    monkeypatch.setattr(hc, "container_restart_count", lambda name: 3)
    assert hc.deploying() == ""
    # Fresh deploy (RestartCount == 0) IS treated as deploying
    monkeypatch.setattr(hc, "container_restart_count", lambda name: 0)
    assert hc.deploying() in hc.CRITICAL_CONTAINERS


def test_healthcheck_html_parser_handles_any_attribute_order():
    hc = _load_healthcheck()
    html = (
        '<!doctype html><html><head>'
        '<link rel="canonical" href="https://trendibizz.com/pricing">'
        '<meta name="description" content="Clear pricing for NZ businesses.">'
        '<meta name="robots" content="index, follow">'
        '</head><body><main><h1>Pricing</h1>' + (" word" * 160) + '</main></body></html>'
    )
    tags = hc._parse_head_tags(html)
    assert tags["canonical"] == "https://trendibizz.com/pricing"
    assert tags["description"] == "Clear pricing for NZ businesses."
    assert tags["robots"] == "index, follow"
    assert tags["h1_count"] == 1
    assert hc.page_quality(html, minimum_words=100) == []


def test_verify_deploy_redeploy_flock_migrate_and_restore_drill():
    vd = (REPO_ROOT / "scripts/vps/verify-deploy.sh").read_text(encoding="utf-8")
    for token in ("Caddyfile", "compose.yml", "Containerfile.*", "_headers", "robots.txt", "api/migrations"):
        assert token in vd, f"verify-deploy.sh missing {token}"

    redeploy = (REPO_ROOT / "scripts/vps/redeploy-api.sh").read_text(encoding="utf-8")
    assert "flock -w" in redeploy

    deploy_api = (REPO_ROOT / "scripts/vps/deploy-api.sh").read_text(encoding="utf-8")
    assert "migrate-api.sh" in deploy_api

    drill = (REPO_ROOT / "scripts/vps/restore-drill.sh").read_text(encoding="utf-8")
    assert "|| true" not in drill.split("pg_restore")[1].splitlines()[0]
    assert "--exit-on-error" in drill
