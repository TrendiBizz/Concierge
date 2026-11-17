#!/usr/bin/env python3
"""Regression tests for the tamper watch.

Run: python3 -m unittest discover -s scripts/security/tamper/tests -v

These cover the 2026-11-17 defects:
  * a section the token cannot read was reported "not in snapshot" (UNCHECKED)
    even when the API said 403, because scopes were a hard-coded list;
  * an empty deployments list (Pages 403) was reported OK;
  * zone settings / rulesets raised false CHANGED when one sub-resource was
    unreadable;
  * Cloudflare's injected challenge loader and CSP nonce placeholder counted as
    site tampering.
"""
import datetime as dt
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAMPER = HERE.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), TAMPER / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dw = load("daily_watch.py")
li = load("live_integrity.py")


def fresh_snapshot(sections, errors, deployments=None):
    snap = {
        "tool": "cf-snapshot.js",
        "version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "sections": sections,
        "errors": errors,
    }
    if deployments is not None:
        snap["deployments"] = deployments
    return snap


class ScopeTests(unittest.TestCase):
    def test_auth_error_detection(self):
        self.assertTrue(dw.auth_error("pages_project: HTTP 403 Authentication error"))
        self.assertTrue(dw.auth_error("worker: HTTP 401 nope"))
        self.assertFalse(dw.auth_error("dns: HTTP 500 boom"))
        self.assertFalse(dw.auth_error(None))

    def test_error_key_mapping(self):
        snap = fresh_snapshot({}, [
            "universal_ssl: HTTP 403 x",
            "user: HTTP 403 x",
            "worker_content: HTTP 403 x",
            "deployments_p1: HTTP 403 x",
        ])
        self.assertEqual(len(dw.section_errors(snap, "zone_settings")), 1)
        self.assertEqual(len(dw.section_errors(snap, "account")), 1)
        self.assertEqual(len(dw.section_errors(snap, "worker")), 1)
        self.assertEqual(len(dw.section_errors(snap, "deployments")), 1)

    def test_missing_scoped_section_is_info_not_unchecked(self):
        """A 403 section is reported as not checked, not "not in snapshot"."""
        snap = fresh_snapshot({}, ["page_shield: HTTP 403 Unauthorized"])
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            rc = dw.run(_args(snap, base))
            report = (base / "_reports" / "daily-watch-latest.txt").read_text()
        self.assertIn("not checked (token cannot read: page_shield: HTTP 403", report)
        self.assertNotIn("not in snapshot (page_shield", report)


class DeploymentTests(unittest.TestCase):
    def test_empty_deployments_is_unchecked_not_ok(self):
        """Pages 403 produced snap.deployments = []; that must not be all-clear."""
        snap = fresh_snapshot(_ok_sections(), [], deployments=[])
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            shutil.copytree(TAMPER / "baselines", base / "_baselines")
            rc = dw.run(_args(snap, base))
            report = (base / "_reports" / "daily-watch-latest.txt").read_text()
        self.assertEqual(rc, 2, report[:500])
        self.assertIn("no deployments in snapshot", report)
        self.assertNotIn("[OK       ] Pages deployments", report)


class PartialSectionTests(unittest.TestCase):
    def test_zone_settings_missing_universal_ssl_is_not_a_change(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "_state").mkdir()
            dw.set_state_dir(base)
            (base / "zone_settings.json").write_text(dw.canon(
                {"min_tls_version": "1.2", "universal_ssl_enabled": True}))
            res = dw.Result("zone_settings")
            dw.compare("zone_settings", {"min_tls_version": "1.2"}, base, res,
                       ignore_missing=True)
        self.assertEqual(res.status, "OK", res.lines)
        self.assertTrue(any("universal_ssl_enabled" in x for x in res.lines))

    def test_ruleset_that_cannot_be_read_is_not_a_change(self):
        entry = {"name": "default", "phase": "http_request_dynamic_redirect",
                 "kind": "zone", "rules": [{"id": "r1", "action": "redirect"}]}
        unread = {**entry, "rules_unreadable": True}
        unread.pop("rules")
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "_state").mkdir()
            dw.set_state_dir(base)
            (base / "rulesets.json").write_text(dw.canon([entry]))
            res = dw.Result("rulesets")
            dw.compare("rulesets", [unread], base, res, drop_unreadable=True)
        self.assertEqual(res.status, "OK", res.lines)


class CloudflareInjectionTests(unittest.TestCase):
    def test_challenge_loader_is_stripped(self):
        expected = b"<html><body>hi</body></html>"
        cap = b"__CF$cv$params"
        loader = (b"<script>(function(){function c(){var b=a.contentDocument||(a.contentWindow&&a.contentWindow.document);"
                  b"d.innerHTML=\"window.__CF$cv$params={r:'x'}\";a.parentNode.appendChild(d)}})();</script>")
        live = b"<html><body>hi" + loader + b"</body></html>"
        out, note = li.strip_cf_challenge(live, expected)
        self.assertIsNone(note)
        self.assertIn(cap, loader)  # the loader really is the shape we target
        self.assertNotEqual(live, expected)
        self.assertLess(len(out), len(live))

    def test_nonce_placeholder_is_ignored(self):
        plain = "default-src 'self'; script-src 'self' https://x"
        nonced = "default-src 'self'; script-src 'self' 'nonce-{CSP_NONCE}' https://x"
        self.assertEqual(li.norm_header("content-security-policy", plain),
                         li.norm_header("content-security-policy", nonced))

    def test_real_csp_change_still_fails(self):
        a = "script-src 'self'"
        b = "script-src 'self' https://evil.example"
        self.assertNotEqual(li.norm_header("content-security-policy", a),
                            li.norm_header("content-security-policy", b))


# ---------------------------------------------------------------- helpers
def _args(snap, base, skip_live=True):
    p = base / "_snapshot.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap))
    # run() writes reports and state next to HERE; point both at the temp dir.
    dw.REPORTS = base / "_reports"
    dw.STATE = base / "_state"
    dw.REPORTS.mkdir(parents=True, exist_ok=True)
    return type("Args", (), {
        "mode": "run", "sections": [], "cf_snapshot": str(p),
        "baselines": str(base / "_baselines"), "max_snapshot_age": 120,
        "skip_live": skip_live, "reason": None,
    })()


def _ok_sections():
    """Sections whose contents match the baselines copied into the temp dir."""
    out = {}
    for p in (TAMPER / "baselines").glob("*.json"):
        if p.name in ("deployments.json",):
            continue
        try:
            out[p.stem] = json.loads(p.read_text())
        except Exception:
            pass
    return out


if __name__ == "__main__":
    unittest.main()
