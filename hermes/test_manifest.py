#!/usr/bin/env python3
"""Checks for the Hermes master manifest and procedures.

Run with the repo's test interpreter:

    /Users/jo/work-staging/venv-concierge/bin/python hermes/test_manifest.py

It does not call a model, the network or the hermes binary.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import install  # noqa: E402

MANIFEST = install.load_manifest()
ROUTINES = {r["id"]: r for r in MANIFEST["routines"]}
PROFILES = MANIFEST["profiles"]

GROK_TRENDI = {
    "Daily site + search monitor (Trendi)",
    "Weekly SEO cycle (Trendi)",
    "Monthly SEO audit (Trendi)",
    "Innovation scout (Trendi)",
    "Trendi LinkedIn weekly draft",
    "Trendi biweekly SEO + security news",
    "Trendi daily SEO / security social drafts",
    "Trendi SEO forums daily deep dive",
    "Twice-monthly post brief (Trendi)",
    "trendibizz.com daily tamper watch",
    "Ego Lite Linux watch",
    "Workwatch weekly report",
}

SECRET_PATTERNS = [
    r"xai-[A-Za-z0-9]{8,}",
    r"sk-[A-Za-z0-9]{10,}",
    r"whsec_[A-Za-z0-9]{8,}",
    r"AIza[0-9A-Za-z_-]{20,}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
    r"Bearer\s+[A-Za-z0-9._-]{20,}",
]


def valid_cron(expr: str) -> bool:
    fields = expr.split()
    if len(fields) != 5:
        return False
    return all(re.fullmatch(r"[\d*/,\-]+", f) for f in fields)


class ManifestTests(unittest.TestCase):
    def test_routine_count_and_ids(self):
        self.assertEqual(len(ROUTINES), 15, "one job per ported routine plus the master")
        self.assertEqual(len(ROUTINES), len(MANIFEST["routines"]), "duplicate routine id")

    def test_profiles_have_souls(self):
        self.assertGreaterEqual(len(PROFILES), 6)
        for name, spec in PROFILES.items():
            self.assertRegex(name, r"^[a-z][a-z0-9-]+$")
            self.assertTrue(spec.get("description"), f"{name}: no description")
            soul = ROOT / spec["soul"]
            self.assertTrue(soul.is_file(), f"{name}: missing {soul}")
            text = soul.read_text(encoding="utf-8")
            self.assertIn("report", text.lower(), f"{name}: SOUL does not mention reporting")

    def test_routine_shape(self):
        for rid, routine in ROUTINES.items():
            with self.subTest(routine=rid):
                self.assertEqual(rid, routine["id"])
                self.assertRegex(rid, r"^[a-z][a-z0-9-]+$")
                self.assertIn(routine["profile"], PROFILES)
                self.assertTrue(routine.get("name"))
                self.assertTrue(routine.get("source"))
                self.assertIn(routine.get("status"), {"active", "paused", "blocked"})
                self.assertIsInstance(routine.get("enabled"), bool)
                self.assertTrue((ROOT / routine["procedure"]).is_file())

    def test_cron_expressions_and_timezone(self):
        for rid, routine in ROUTINES.items():
            with self.subTest(routine=rid):
                self.assertTrue(valid_cron(routine["schedule"]), routine["schedule"])
                self.assertEqual(
                    routine.get("timezone", MANIFEST["timezone"]), "Pacific/Auckland"
                )

    def test_enabled_matches_status(self):
        for rid, routine in ROUTINES.items():
            with self.subTest(routine=rid):
                if routine["enabled"]:
                    self.assertEqual(routine["status"], "active", f"{rid}: enabled but {routine['status']}")
                else:
                    self.assertIn(routine["status"], {"paused", "blocked"})
                    self.assertTrue(routine.get("paused_reason"), f"{rid}: paused without a reason")

    def test_procedures_have_approval_guard(self):
        for rid, routine in ROUTINES.items():
            with self.subTest(routine=rid):
                text = (ROOT / routine["procedure"]).read_text(encoding="utf-8")
                self.assertTrue(text.startswith("# Routine:"), f"{rid}: no routine heading")
                self.assertRegex(text, r"(?m)^- Approval:", f"{rid}: no Approval line")
                self.assertIn(
                    f"- Profile: `{routine['profile']}`",
                    text,
                    f"{rid}: procedure profile does not match the manifest",
                )
                self.assertIn(routine["schedule"], text, f"{rid}: procedure schedule mismatch")
                self.assertRegex(
                    text.lower(),
                    r"(never send|do not send|draft only|drafts only|read-only|"
                    r"research and advice only|report only|brief only|watch only|"
                    r"audits only|ideas only|nothing is posted|never post|"
                    r"never change cloudflare|no site changes)",
                    f"{rid}: no approval/safety guard",
                )

    def test_grok_automation_coverage(self):
        mapped = {entry["name"]: entry["routine"] for entry in MANIFEST["grok_automations"]}
        self.assertEqual(set(mapped), GROK_TRENDI, "the Grok Trendi automation list drifted")
        for name, rid in mapped.items():
            with self.subTest(automation=name):
                self.assertIn(rid, ROUTINES, f"{name}: unknown routine {rid}")
        covered = set(mapped.values())
        for rid, routine in ROUTINES.items():
            if not rid.startswith("master-") and rid != "appsec-weekly-advisories":
                self.assertIn(rid, covered, f"{rid}: not mapped to a Grok automation")

    def test_master_routines(self):
        self.assertIn("master-daily-brief", ROUTINES)
        self.assertIn("master-weekly-review", ROUTINES)
        self.assertEqual(ROUTINES["master-daily-brief"]["profile"], "trendi-master")
        self.assertEqual(ROUTINES["master-weekly-review"]["profile"], "trendi-master")
        self.assertTrue(ROUTINES["master-daily-brief"]["enabled"])

    def test_no_duplicate_profile_schedule(self):
        seen = set()
        for rid, routine in ROUTINES.items():
            if not routine["enabled"]:
                continue
            key = (routine["profile"], routine["schedule"])
            self.assertNotIn(key, seen, f"{rid}: duplicate schedule {key}")
            seen.add(key)

    def test_no_secret_shaped_strings(self):
        files = [
            ROOT / "README.md",
            ROOT / "AGENTS.md",
            ROOT / "JOBS.md",
            ROOT / "schedules.yaml",
            *sorted((ROOT / "profiles").rglob("*.md")),
            *sorted((ROOT / "routines").rglob("*.md")),
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            for pattern in SECRET_PATTERNS:
                with self.subTest(file=path.name, pattern=pattern):
                    self.assertIsNone(
                        re.search(pattern, text), f"{path}: secret-shaped string {pattern}"
                    )

    def test_approved_parity_schedules(self):
        expected = {
            "seo-daily-monitor": "30 7 * * *",
            "seo-weekly-cycle": "0 8 * * 1",
            "trendi-linkedin-weekly": "0 9 * * 1",
            "trendi-biweekly-news": "0 9 1,15 * *",
            "appsec-weekly-advisories": "0 9 * * 3",
        }
        for rid, schedule in expected.items():
            self.assertEqual(ROUTINES[rid]["schedule"], schedule)
        self.assertEqual(ROUTINES["appsec-weekly-advisories"]["profile"], "appsec")

    def test_report_completion_contract(self):
        for rid, routine in ROUTINES.items():
            with self.subTest(routine=rid):
                procedure = (ROOT / routine["procedure"]).read_text(encoding="utf-8")
                target = f"/opt/data/.workwatch/reports/hermes/{routine['profile']}/<YYYY-MM-DD>-{rid}.md"
                prompt = install.build_prompt(MANIFEST, routine, procedure)
                for text in (procedure, prompt.split("---", 1)[0]):
                    self.assertIn(target, text)
                    self.assertIn("Pacific/Auckland", text)
                    self.assertIn("read back", text)
                    self.assertIn("WRITE FAILED", text)
                self.assertIn("ZoneInfo", prompt)
                self.assertIn("write_file", prompt)
                self.assertIn("[CRON_FAILURE]", prompt)

    def test_prompt_includes_procedure_and_guard(self):
        routine = ROUTINES["seo-daily-monitor"]
        text = (ROOT / routine["procedure"]).read_text(encoding="utf-8")
        prompt = install.build_prompt(MANIFEST, routine, text)
        self.assertIn(routine["id"], prompt)
        self.assertIn("AGENTS.md", prompt)
        self.assertIn("Do not send, post, deploy", prompt)
        self.assertIn("daily_monitor.py", prompt)


class PlanTests(unittest.TestCase):
    def _actions(self, home: Path, **kwargs):
        return install.plan(MANIFEST, home, **kwargs)

    def test_plan_on_empty_home_is_pure(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "hermes-home"
            actions = self._actions(home)
            self.assertFalse(home.exists(), "plan must not create the home")
            profiles = [a for a in actions if a["kind"] == "profile"]
            souls = [a for a in actions if a["kind"] == "soul"]
            jobs = [a for a in actions if a["kind"] == "job"]
            self.assertEqual(len(profiles), len(PROFILES))
            self.assertEqual(len(souls), len(PROFILES))
            self.assertEqual(len(jobs), len(ROUTINES))
            self.assertTrue(all(a["action"] == "create" for a in jobs))

    def test_plan_replaces_then_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "hermes-home"
            pdir = home / "profiles" / "seo-engine" / "cron"
            pdir.mkdir(parents=True)
            (pdir / "jobs.json").write_text(
                json.dumps({"jobs": [{"id": "abc123", "name": "seo-daily-monitor"}]}),
                encoding="utf-8",
            )
            actions = self._actions(home)
            job = next(a for a in actions if a.get("name") == "seo-daily-monitor")
            self.assertEqual(job["action"], "replace")

            state = {"seo-daily-monitor": {"hash": job["hash"]}}
            actions = self._actions(home, state=state)
            job = next(a for a in actions if a.get("name") == "seo-daily-monitor")
            self.assertEqual(job["action"], "skip")

    def test_plan_includes_links_for_every_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "hermes-home"
            actions = self._actions(home)
            links = [a for a in actions if a["kind"] == "links"]
            self.assertEqual(len(links), len(PROFILES))
            self.assertEqual({a["name"] for a in links}, set(PROFILES))

    def test_ensure_profile_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "hermes-home"
            install.ensure_profile_links(home, "seo-engine")
            for rel, target in install.PROFILE_LINKS.items():
                link = home / "profiles" / "seo-engine" / "home" / rel
                self.assertTrue(link.is_symlink(), f"{rel} is not a symlink")
                self.assertEqual(os.readlink(link), str(home / target))

    def test_ensure_profile_links_does_not_replace_a_real_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "hermes-home"
            real = home / "profiles" / "seo-engine" / "home" / ".config" / "trendi"
            real.mkdir(parents=True)
            (real / "kept.txt").write_text("keep", encoding="utf-8")
            install.ensure_profile_links(home, "seo-engine")
            self.assertTrue((real / "kept.txt").exists(), "a real directory was removed")
            self.assertFalse(real.is_symlink())

    def test_plan_includes_master_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "hermes-home"
            actions = self._actions(home)
            scripts = [a for a in actions if a["kind"] == "script"]
            self.assertEqual(len(scripts), 1)
            self.assertEqual(scripts[0]["name"], "trendi-master/lane_status.py")
            self.assertTrue(scripts[0]["source"].is_file())
            self.assertEqual(scripts[0]["target"].name, "lane_status.py")

    def test_workwatch_is_active(self):
        self.assertTrue(ROUTINES["workwatch-weekly-report"]["enabled"])
        self.assertEqual(ROUTINES["workwatch-weekly-report"]["status"], "active")
        self.assertIn("- Profile: `workwatch`", (ROOT / "routines/workwatch-weekly-report.md").read_text(encoding="utf-8"))

    def test_only_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "hermes-home"
            actions = self._actions(home, only={"seo-daily-monitor"})
            jobs = [a for a in actions if a["kind"] == "job"]
            self.assertEqual([a["name"] for a in jobs], ["seo-daily-monitor"])
            # profiles/SOULs are still ensured
            self.assertEqual(len([a for a in actions if a["kind"] == "profile"]), len(PROFILES))

    def test_desired_hash_changes_with_schedule(self):
        routine = dict(ROUTINES["seo-daily-monitor"])
        text = (ROOT / routine["procedure"]).read_text(encoding="utf-8")
        prompt = install.build_prompt(MANIFEST, routine, text)
        first = install.desired_hash(MANIFEST, routine, prompt)
        routine["schedule"] = "41 7 * * *"
        second = install.desired_hash(MANIFEST, routine, prompt)
        self.assertNotEqual(first, second)


class LaneStatusTests(unittest.TestCase):
    SCRIPT = ROOT / "scripts" / "lane_status.py"

    def _load(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("lane_status", self.SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_expected_matches_manifest(self):
        module = self._load()
        for rid, routine in ROUTINES.items():
            if rid.startswith("master-"):
                continue
            if routine["enabled"]:
                self.assertIn(
                    rid,
                    module.EXPECTED[routine["profile"]],
                    f"{rid}: an active routine is missing from lane_status.EXPECTED",
                )
        for profile, ids in module.EXPECTED.items():
            for rid in ids:
                self.assertIn(rid, ROUTINES, f"lane_status knows {rid}, the manifest does not")
                self.assertEqual(ROUTINES[rid]["profile"], profile)
        for profile in module.PAUSED:
            for rid in module.EXPECTED[profile]:
                self.assertFalse(
                    ROUTINES[rid]["enabled"],
                    f"{profile} is listed PAUSED but {rid} is enabled",
                )
        self.assertNotIn("workwatch", module.PAUSED, "Workwatch is active in Hermes")

    def _run(self, reports: Path):
        import subprocess

        env = {**os.environ, "HERMES_REPORTS": str(reports)}
        return subprocess.run(
            [sys.executable, str(self.SCRIPT)],
            check=True,
            text=True,
            capture_output=True,
            env=env,
        ).stdout

    def test_placeholder_latest_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp)
            lane = reports / "trendi-desk"
            lane.mkdir(parents=True)
            (lane / "latest.md").write_text("# trendi-desk — 2026-11-17\nStatus: quiet\n", encoding="utf-8")
            out = self._run(reports)
            self.assertIn("trendi-desk | NO REPORT", out)
            self.assertIn("appsec | NO REPORT", out)
            self.assertIn("placeholder latest.md ignored", out)
            self.assertIn("ANSWERED: 0/5", out)

    def test_real_dated_report_is_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp)
            lane = reports / "seo-engine"
            lane.mkdir(parents=True)
            (lane / "2026-11-17-seo-daily-monitor.md").write_text(
                "# seo-daily-monitor — 2026-11-17\nStatus: quiet\n", encoding="utf-8"
            )
            (lane / "latest.md").write_text("# seo-daily-monitor — 2026-11-17\nStatus: quiet\n", encoding="utf-8")
            out = self._run(reports)
            self.assertIn("seo-engine | quiet | seo-daily-monitor", out)
            self.assertIn("ANSWERED: 1/5", out)

    def test_stale_report_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp)
            lane = reports / "seo-engine"
            lane.mkdir(parents=True)
            path = lane / "2026-11-17-seo-daily-monitor.md"
            path.write_text("# seo-daily-monitor — 2026-11-17\nStatus: quiet\n", encoding="utf-8")
            old = path.stat().st_mtime - 48 * 3600
            os.utime(path, (old, old))
            out = self._run(reports)
            self.assertIn("seo-engine | NO REPORT", out)
            self.assertIn("ANSWERED: 0/5", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
