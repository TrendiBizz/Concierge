"""Every outreach send script must carry the do-not-contact guard, and no script may target a blocked domain. No network."""
import csv, glob, re, unittest
from pathlib import Path

B = Path(__file__).resolve().parent / "backlinks"


class DoNotContact(unittest.TestCase):
    def blocked(self):
        return [r["domain"] for r in csv.DictReader(open(B / "do-not-contact.csv"))]

    def test_every_send_script_guarded(self):
        scripts = sorted(glob.glob(str(B / "send_*.py")))
        self.assertTrue(scripts)
        for p in scripts:
            t = open(p).read()
            for d in self.blocked():
                self.assertIn(d, t, f"{p} missing {d} in DNC")
            self.assertIn("_ok(m[\"To\"])", t, f"{p} sends without the guard")
            self.assertEqual(t.count("send_message("), t.count("_ok(m[\"To\"]); s.send_message("), p)

    def test_no_script_targets_blocked_domain(self):
        for p in glob.glob(str(B / "send_*.py")):
            for e in re.findall(r"[\w.+-]+@([\w.-]+)", open(p).read().split("with smtplib")[0].split("DNC =")[0]):
                for d in self.blocked():
                    self.assertFalse(e.lower().endswith(d), f"{p} targets {e}")

    def test_pipeline_has_no_blocked_rows(self):
        for d in self.blocked():
            rows = [r for r in csv.DictReader(open(B / "prospects.csv")) if d in r["domain"] and r["status"] != "do-not-contact"]
            self.assertEqual(rows, [], d)


if __name__ == "__main__":
    unittest.main()
