"""A customer's IFC must not be able to kill the process reading it.

ifcopenshell is a C extension; a malformed model segfaults the interpreter. Measuring inside the
API process therefore meant one bad export took down the worker serving every other customer.
The measuring now runs in a child process, so these tests assert the contract that keeps the API
alive: a crashed, timed-out, or erroring child becomes an exception the endpoint reports.
"""

import json
import subprocess

import pytest

from app import designs

pytestmark = pytest.mark.anyio


def _completed(returncode, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=["python", "-m", "app.ifc_takeoff"], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def test_a_segfaulting_model_is_reported_and_does_not_kill_the_caller(monkeypatch):
    """The whole point: returncode -11 (SIGSEGV) arrives as a message, not as our own death."""
    monkeypatch.setattr(designs.subprocess, "run", lambda *a, **k: _completed(-11, stderr=""))
    with pytest.raises(RuntimeError) as caught:
        designs._takeoff("/tmp/whatever.ifc")
    assert "crashed" in str(caught.value)
    assert "re-export" in str(caught.value)


def test_a_model_that_takes_too_long_is_reported(monkeypatch):
    def explode(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="python", timeout=120)
    monkeypatch.setattr(designs.subprocess, "run", explode)
    with pytest.raises(RuntimeError) as caught:
        designs._takeoff("/tmp/slow.ifc")
    assert "took too long" in str(caught.value)


def test_an_errored_child_reports_its_reason(monkeypatch):
    payload = json.dumps({"error": "unsupported schema"})
    monkeypatch.setattr(designs.subprocess, "run", lambda *a, **k: _completed(1, stdout=payload))
    with pytest.raises(RuntimeError) as caught:
        designs._takeoff("/tmp/odd.ifc")
    assert "unsupported schema" in str(caught.value)


def test_a_good_model_is_measured(monkeypatch):
    payload = json.dumps({"wall_count": 2, "gross_wall_area_m2": 24.5, "net_wall_area_m2": 22.0,
                          "opening_count": 1, "opening_area_m2": 1.5,
                          "net_cladding_area_m2": 20.5, "note": ""})
    monkeypatch.setattr(designs.subprocess, "run", lambda *a, **k: _completed(0, stdout=payload))
    summary = designs._takeoff("/tmp/good.ifc")
    assert summary["net_cladding_area_m2"] == 20.5
    assert summary["wall_count"] == 2


def test_the_measuring_runs_out_of_process():
    """Guards the fix itself: if someone moves the ifcopenshell import back in-process, this fails."""
    source = (designs.__file__ and open(designs.__file__).read()) or ""
    assert "ifcopenshell" not in source, "ifcopenshell must only be imported by app.ifc_takeoff"
    assert "app.ifc_takeoff" in source
