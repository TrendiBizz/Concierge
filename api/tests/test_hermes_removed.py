"""Hermes was removed 2026-11-21: schema.sql must not recreate its tables; migration 0002 drops them."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_schema_does_not_create_hermes_tables():
    assert "hermes_" not in (ROOT / "app" / "schema.sql").read_text().replace("hermes_* tables were dropped", "")


def test_migration_0002_chain_and_drops():
    path = ROOT / "migrations" / "versions" / "0002_drop_hermes_tables.py"
    spec = importlib.util.spec_from_file_location("m0002", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (mod.revision, mod.down_revision) == ("0002", "0001")
    stmts = []
    mod.op = type("Op", (), {"execute": staticmethod(stmts.append)})
    mod.upgrade()
    assert [s.split()[-1] for s in stmts] == ["hermes_actions", "hermes_case_state", "hermes_tenant_settings"]
