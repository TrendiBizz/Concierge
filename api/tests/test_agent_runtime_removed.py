"""Retirement contract: owned services cannot silently restart the removed agent."""
from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_agent_installers_and_runtime_entrypoints_are_removed():
    for relative in (
        "hermes/install.py", "hermes/runtime/start-master.sh",
        "concierge-stack/hermes/start-hermes.sh", "concierge-stack/hermes/ask-hermes.sh",
        "scripts/vps/hermes.sh", "scripts/vps/compose.hermes.yml",
        "scripts/vps/hermes.customer.toolsets.yaml",
    ):
        assert not (ROOT / relative).is_file(), relative


def test_runtime_is_not_an_application_dependency_or_implicit_planner():
    assert not any("hermes" in name.lower() for name in Settings.model_fields)
    source = (ROOT / "concierge-stack/action-gateway/src/main.rs").read_text()
    assert 'need("PLANNER_BASE_URL")?' in source
    assert 'need("PLANNER_MODEL")?' in source
    assert "8642" not in source
    assert not (ROOT / "api/app/hermes_ops.py").exists()
    assert not (ROOT / "api/app/hermes_orchestrator.py").exists()
