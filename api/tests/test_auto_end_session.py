"""Tests for auto-end-session.py.

These are written to be falsifiable. Each guardrail test was checked by
deliberately breaking the code it covers and confirming the test goes red --
four tests in the previous session passed against broken code.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "auto-end-session.py"


def load_module():
    spec = importlib.util.spec_from_file_location("auto_end_session", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load_module()


# --------------------------------------------------------------------------
# The counter trap: occupancy must come from pressure/window, never lifetime.
# --------------------------------------------------------------------------


def test_statusbar_percentage_is_occupancy_and_tokens_are_not():
    lifetime, fraction = mod.parse_statusbar("11.3M tok · 29%")
    assert lifetime == 11_300_000
    assert fraction == pytest.approx(0.29)
    # The real trap: treating the lifetime figure as occupancy would be absurd.
    assert mod.occupancy(lifetime, 1_048_576) > 10.0
    assert fraction < 1.0


def test_lifetime_total_cannot_be_compared_to_window():
    """11.3M against a 1,048,576 window is 1078%, not 29%."""
    assert mod.occupancy(11_300_000, 1_048_576) == pytest.approx(10.776, rel=1e-3)


def test_parse_statusbar_handles_k_and_plain():
    assert mod.parse_statusbar("900K tok · 12%")[0] == 900_000
    assert mod.parse_statusbar("500 tok · 1%")[0] == 500


def test_parse_statusbar_without_token_figure_raises():
    with pytest.raises(ValueError):
        mod.parse_statusbar("29% only")


def test_parse_statusbar_without_percentage_raises():
    with pytest.raises(ValueError):
        mod.parse_statusbar("11.3M tok")


# --------------------------------------------------------------------------
# Trigger
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pressure,expected",
    [
        (0, False),
        (100_000, False),      # ~9.5%
        (838_860, False),      # 0.79999923 -- just BELOW; must not fire
        (838_861, True),       # first integer token at or above 80%
        (900_000, True),       # ~86%
        (1_048_576, True),     # 100%
    ],
)
def test_trigger_fires_at_threshold(pressure, expected):
    fraction = mod.occupancy(pressure, 1_048_576)
    assert mod.should_end(fraction, 0.80) is expected


def test_threshold_boundary_is_inclusive():
    """Exactly at threshold fires; one token under does not."""
    window = 1_000_000
    assert mod.should_end(mod.occupancy(800_000, window), 0.80) is True
    assert mod.should_end(mod.occupancy(799_999, window), 0.80) is False


def test_trigger_respects_custom_threshold():
    fraction = mod.occupancy(500_000, 1_048_576)
    assert mod.should_end(fraction, 0.40) is True
    assert mod.should_end(fraction, 0.90) is False


def test_occupancy_rejects_zero_window():
    with pytest.raises(ValueError):
        mod.occupancy(100, 0)


# --------------------------------------------------------------------------
# Exclusions -- the paths the handoff says must never be committed
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "QA/verification/HERMES_CHANNEL_AUDIT_2026-11-09.json",
        "QA/verification/HERMES_CONCIERGE_FRAMEWORK_2026-11-09.md",
        "QA/verification/HERMES_ORCHESTRATION_RESEARCH_2026-11-09.md",
        "QA/verification/HERMES_FRAMEWORK_2026-11-09.md",
        "office-shots/shot1.png",
        "tiktok-review/clip.mp4",
    ],
)
def test_excluded_paths_are_recognised(path):
    assert mod.excluded(path) is True


def test_ordinary_docs_are_not_excluded():
    assert mod.excluded("QA/verification/HANDOFF.md") is False
    assert mod.excluded("api/portal.py") is False


def test_excluded_staged_path_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "staged_paths", lambda repo: ["QA/verification/HERMES_X.md"])
    with pytest.raises(mod.Refused, match="excluded path is staged"):
        mod.check_staged_are_expected(tmp_path)


def test_unexpected_staged_path_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "staged_paths", lambda repo: ["secrets/prod.env"])
    with pytest.raises(mod.Refused, match="unexpected staged path"):
        mod.check_staged_are_expected(tmp_path)


def test_allowlisted_staged_paths_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(
        mod,
        "staged_paths",
        lambda repo: ["QA/verification/HANDOFF.md", "api/portal.py", "scripts/rust-gate.sh"],
    )
    mod.check_staged_are_expected(tmp_path)  # must not raise


# --------------------------------------------------------------------------
# Gates block the push
# --------------------------------------------------------------------------


def test_red_test_gate_blocks(monkeypatch, tmp_path):
    class Result:
        returncode = 1
        stdout = "1 failed"
        stderr = ""

    monkeypatch.setattr(mod, "run", lambda *a, **k: Result())
    with pytest.raises(mod.Refused, match="pytest gate FAILED"):
        mod.run_gates(tmp_path)


def test_green_gates_pass(monkeypatch, tmp_path):
    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(mod, "run", lambda *a, **k: Result())
    mod.run_gates(tmp_path)  # Python suite green and no Rust gate to run


# --------------------------------------------------------------------------
# Push rejection must stop without force
# --------------------------------------------------------------------------


def test_rejected_push_stops_without_force(monkeypatch, tmp_path):
    seen: list[list[str]] = []

    class Result:
        def __init__(self, rc=0, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def fake_run(args, **kwargs):
        seen.append(args)
        if args[:2] == ["git", "commit"]:
            return Result(0)
        if args[:2] == ["git", "push"]:
            return Result(1, err="! [rejected] main -> main (non-fast-forward)")
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return Result(0, out="abc123\n")
        if args[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return Result(0, out="main\n")
        return Result(0)

    monkeypatch.setattr(mod, "run", fake_run)
    monkeypatch.setattr(mod, "check_staged_are_expected", lambda repo: None)
    monkeypatch.setattr(mod, "staged_paths", lambda repo: ["QA/verification/x.md"])
    monkeypatch.setattr(mod, "run_gates", lambda repo: None)

    with pytest.raises(mod.Refused, match="push REJECTED"):
        mod.commit_and_push(tmp_path, "msg", dry_run=False)

    pushes = [a for a in seen if a[:2] == ["git", "push"]]
    assert pushes, "expected a push attempt"
    for args in pushes:
        assert "--force" not in args
        assert "-f" not in args


def test_dry_run_never_commits_or_pushes(monkeypatch, tmp_path):
    seen: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args, **kwargs):
        seen.append(args)
        if args[:3] == ["git", "diff", "--cached"]:
            return Result()
        return Result()

    monkeypatch.setattr(mod, "run", fake_run)
    monkeypatch.setattr(mod, "check_staged_are_expected", lambda repo: None)
    monkeypatch.setattr(mod, "staged_paths", lambda repo: ["QA/verification/x.md"])
    monkeypatch.setattr(mod, "run_gates", lambda repo: None)

    out = mod.commit_and_push(tmp_path, "msg", dry_run=True)
    assert out["committed"] is False and out["pushed"] is False
    assert not [a for a in seen if a[:2] in (["git", "commit"], ["git", "push"])]


def test_nothing_staged_is_a_no_op(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "staged_paths", lambda repo: [])
    out = mod.commit_and_push(tmp_path, "msg", dry_run=False)
    assert out == {"committed": False, "pushed": False, "reason": "nothing staged"}


# --------------------------------------------------------------------------
# End-to-end via CLI
# --------------------------------------------------------------------------


def test_cli_below_threshold_exits_zero_without_touching_git(tmp_path):
    out = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--repo", str(tmp_path),
            "--pressure", "100000",
            "--window", "1048576",
            "--json",
        ],
        capture_output=True, text=True, check=False,
    )
    assert out.returncode == 0, out.stderr
    assert '"ended": false' in out.stdout
    assert "below threshold" in out.stdout


def test_cli_from_statusbar_uses_percentage_not_lifetime(tmp_path):
    """The whole point: 11.3M tok must not be read as occupancy."""
    out = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--repo", str(tmp_path),
            "--from-statusbar", "11.3M tok · 29%",
            "--threshold", "0.80",
            "--json",
        ],
        capture_output=True, text=True, check=False,
    )
    assert out.returncode == 0, out.stderr
    assert '"occupancy": 0.29' in out.stdout
    assert '"lifetime_tokens_ignored": 11300000' in out.stdout
    assert '"ended": false' in out.stdout


def test_cli_statusbar_at_high_pressure_still_roughly_parses(tmp_path):
    out = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--repo", str(tmp_path),
            "--from-statusbar", "11.3M tok · 95%",
            "--json",
        ],
        capture_output=True, text=True, check=False,
    )
    assert out.returncode in (0, 1), out.stderr
    assert '"occupancy": 0.95' in out.stdout


def test_cli_missing_args_exits_two():
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--pressure", "900000"],
        capture_output=True, text=True, check=False,
    )
    assert out.returncode == 2


def test_trigger_stages_the_workspace_before_commit(monkeypatch, tmp_path):
    """The end sequence must `git add -A` first, or an auto-end never commits
    unstaged work (the original build forgot the stage step)."""
    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    calls: list[list[str]] = []
    monkeypatch.setattr(mod, "run", lambda args, cwd: (calls.append(args) or Result()))
    monkeypatch.setattr(mod, "commit_and_push", lambda repo, msg, dry_run: {"committed": False, "reason": "stub"})

    rc = mod.main(["--repo", str(tmp_path), "--pressure", "90", "--window", "100", "--json"])
    assert rc == 0
    assert ["git", "add", "-A"] in calls, "auto-end must stage before committing"
